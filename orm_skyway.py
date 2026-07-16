#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2025 Software Tree, LLC. All Rights Reserved.
# See LICENSE for license terms.
"""
ORM_Skyway Workflow
==========================================
Run this script from the PROJECT ROOT DIRECTORY (your service project directory,
not the directory where this script lives).

Project layout created beneath the current directory:
  config/    ORM specs (.config, .revjdx, .jdx), JDBC driver copy
  src/       Generated .java model classes (<package path>)
  bin/       Compiled .class files (<package path>)
  *.bat/.sh  Helper scripts

WORKFLOW
--------
  Phase 1  -- Reverse-engineer the database schema into a JDX object model  (script)
  Phase 2  -- Refine & curate the .jdx ORM spec and verify with JDXDemo  (manual, optional but recommended)
  Phase 3  -- Package the model into a Gilhari RESTful microservice Docker image  (script)

USAGE
-----
  # Run Phase 1 only (stop for optional manual refinement before Phase 3)
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json --phase 1

  # Run Phase 3 only (after optional Phase 2 work is done)
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json --phase 3

  # Run Phase 1 then Phase 3 in one go (skipping Phase 2)
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json --phase 1+3

  # Default (no --phase flag) is equivalent to --phase 1+3
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json

  # List available tables without writing any files
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json --phase introspect

  # Non-interactive run (auto-accept all prompts)
  python C:\\tools\\orm_skyway_automation\\orm_skyway.py -f orm_skyway_config.json --yes

  On macOS / Linux, replace C:\\tools\\orm_skyway_automation\\ with ~/tools/orm_skyway_automation/

PREREQUISITES
-------------
  Phase 1: Python 3.8+, JDK 8+ on PATH, Gilhari SDK (includes JDX ORM libraries),
           JDBC driver JAR for your database
  Phase 3: Python 3.8+, Docker Desktop (Windows/Mac) or Docker daemon (Linux) running.
           Phase 1 must have been run first (bin/ and config/ must exist).
  Optional: pip install rich   (nicer terminal output with colours)

  Or skip local prerequisites entirely and run inside the softwaretree/orm_skyway
  Docker image (bundles Python, JDK, JDX, and rich). See run_orm_skyway.sh/.cmd.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

__version__ = "1.0.23"

# ── Optional pretty output ────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    console = Console()
    def header(msg):  console.print(Panel(f"[bold cyan]{msg}[/bold cyan]"))
    def info(msg):    console.print(f"[green]✔[/green] {msg}")
    def warn(msg):    console.print(f"[yellow]⚠[/yellow]  {msg}")
    def error(msg):   console.print(f"[red]✘[/red] {msg}")
    def ask(prompt, default=None):
        console.print()
        try:
            return Prompt.ask(f"[bold]{prompt}[/bold]", default=default)
        except EOFError:
            if default is not None:
                verbose_info(f"Non-TTY stdin — using default: {default}")
                return default
            raise
    def ask_yn(prompt, default=True):
        console.print()
        try:
            return Confirm.ask(f"[bold]{prompt}[/bold]", default=default)
        except EOFError:
            verbose_info(f"Non-TTY stdin — using default: {default}")
            return default
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    def header(msg):  print(f"\n{'='*60}\n  {msg}\n{'='*60}")
    def info(msg):    print(f"  [OK] {msg}")
    def warn(msg):    print(f"  [!!] {msg}")
    def error(msg):   print(f"  [XX] {msg}", file=sys.stderr)
    def ask(prompt, default=None):
        suffix = f" [{default}]" if default is not None else ""
        try:
            return input(f"\n{prompt}{suffix}: ").strip() or default
        except EOFError:
            if default is not None:
                return default
            raise
    def ask_yn(prompt, default=True):
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            ans = input(f"\n{prompt} {suffix}: ").strip().lower()
            return default if ans == "" else ans in ("y", "yes")
        except EOFError:
            return default

IS_WINDOWS = platform.system() == "Windows"

def write_sh(path: Path, text: str):
    """Write a shell script with Unix line endings (LF only).
    Ensures .sh files work on macOS/Linux even when generated on Windows.

    Uses open(..., newline="\\n") rather than Path.write_text(..., newline=...) —
    the latter only gained a newline= parameter in Python 3.10+. The
    softwaretree/orm_skyway Docker image (Ubuntu 20.04) ships Python 3.8,
    so this needs to work down to 3.8 as well as natively on the host.
    """
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    path.chmod(0o755)

def phase_separator(title: str):
    """Print a prominent visual band to mark the start of a new phase."""
    if HAS_RICH:
        width = console.width or 80
        bar = "═" * width
        line = f"  {title}"
        console.print(f"\n[bold yellow]{bar}[/bold yellow]", justify="left")
        console.print(f"[bold yellow]{line}[/bold yellow]", justify="left")
        console.print(f"[bold yellow]{bar}[/bold yellow]\n", justify="left")
    else:
        width = 80
        bar = "═" * width
        print(f"\n{bar}")
        print(f"  {title}")
        print(f"{bar}\n")
SEP = ";" if IS_WINDOWS else ":"

# Fixed subdirectory names — matches standard JDX/Gilhari project layout
SRC_DIR    = "src"
BIN_DIR    = "bin"
CONFIG_DIR = "config"

# Verbose output flag — set to True via --verbose flag or "verbose": true in config
_VERBOSE = False

# ==============================================================================
# FA1.  DOCKER-CONTAINER SELF-DETECTION  (softwaretree/orm_skyway image)
# ==============================================================================
#
# When orm_skyway.py itself runs inside the softwaretree/orm_skyway container
# (instead of directly on the developer's machine), any JDBC URL that points at
# "localhost" / "127.0.0.1" actually means "the host machine running Docker" —
# not the container itself. Substituting host.docker.internal lets Phase 1
# (live database introspection / reverse engineering) reach a database running
# on the host without any change to orm_skyway_config.json. This mirrors the
# logic already used to build the .docker.jdx file for the Gilhari image.

def _running_in_docker() -> bool:
    """Return True when this process is executing inside a Docker container.

    Path("/.dockerenv") is created by the Docker runtime in every Linux
    container (Docker Engine, Docker Desktop's Linux VM, Colima, Podman's
    Docker-compat mode, etc.) — reliable across runtimes, no env var needed.
    """
    return Path("/.dockerenv").exists()


def _docker_safe_jdbc_url(jdbc_url: str) -> str:
    """Rewrite localhost/127.0.0.1 -> host.docker.internal in a JDBC URL.

    Safe to call unconditionally — URLs that don't reference localhost
    (remote servers, other containers by name, file-based DBs like SQLite)
    pass through unchanged.
    """
    rewritten = jdbc_url
    for _host in ("localhost", "127.0.0.1"):
        rewritten = rewritten.replace(f"//{_host}:", "//host.docker.internal:")
        rewritten = rewritten.replace(f"//{_host}/", "//host.docker.internal/")
    return rewritten


def _detect_docker_platform() -> str:
    """Best-effort default for --platform on `docker build` / `docker run`.

    softwaretree/gilhari is published for both linux/amd64 and linux/arm64.
    Previously the scripts hardcoded linux/amd64, which fails to start on
    Apple Silicon (M1/M2/M3/M4) Macs — the image builds under amd64 emulation
    but the container then fails to run correctly. Detect the host CPU
    architecture and pick the matching platform; still overridable via
    --docker-platform / "docker_platform" in the config file for anyone who
    deliberately wants to target the other architecture (e.g. building an
    amd64 image on Apple Silicon for deployment to an amd64 server).
    """
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "linux/arm64"
    return "linux/amd64"


# The softwaretree/gilhari base image (which softwaretree/orm_skyway builds on)
# bundles the JDX SDK at this fixed path — confirmed via:
#   docker run --rm softwaretree/gilhari find / -iname "jxclasses.jar"
#   -> /node/node_modules/jdxnode/libs/jxclasses.jar
# A host-side jx_home value (e.g. "C:/SoftwareTree/JDX5.x") is meaningless
# inside the container — only /project (the bind-mounted project directory)
# exists there. When running inside softwaretree/orm_skyway, always use the
# image's own bundled SDK instead of whatever jx_home the config/CLI supplied.
_DOCKER_JX_HOME = "/node/node_modules/jdxnode"


def _container_path_to_host(container_abs_path: Path, root: Path, what: str = "path"):
    """Translate an absolute in-container path under the project mount
    (root, normally /project) back to the real host-side path, using
    ORM_SKYWAY_HOST_PROJECT_DIR (exported by run_orm_skyway.sh/.cmd with the
    real %cd%/$(pwd)). Returns a string path, or None if translation isn't
    possible (not running in Docker, the path is outside the project root,
    or the env var isn't set) — callers decide whether that's fatal.

    `what` is used only in the warning message to identify what's being
    translated (e.g. "DB file directory", "JDX sandbox directory").
    """
    if not _running_in_docker():
        return str(container_abs_path)
    host_root_env = os.environ.get("ORM_SKYWAY_HOST_PROJECT_DIR")
    if not host_root_env:
        warn(
            f"Running inside Docker but ORM_SKYWAY_HOST_PROJECT_DIR is not set — "
            f"cannot translate the {what} to a host path. Use the latest "
            f"run_orm_skyway.sh/.cmd, which set this automatically."
        )
        return None
    try:
        rel = container_abs_path.relative_to(root)
    except ValueError:
        warn(
            f"The {what} is outside the project root and ORM_SKYWAY_HOST_PROJECT_DIR "
            f"can't be used to translate it to a host path."
        )
        return None
    return str(Path(host_root_env.replace("\\", "/")) / rel)

# Gilhari/JDX ships several common JDBC driver JARs in external_libs/ alongside
# the SDK itself (confirmed under _DOCKER_JX_HOME/external_libs in the image).
# Exact filenames are version-specific and may change release to release, so
# match by glob pattern rather than a hardcoded filename. Patterns are tried
# in order; the first pattern with any match wins (covers e.g. MySQL having
# both a current "mysql-connector-j-*" and a legacy "mysql-connector-java-*"
# naming convention shipped side by side).
_BUNDLED_DRIVER_PATTERNS = {
    "MYSQL":    ["mysql-connector-j-*.jar", "mysql-connector-java-*.jar"],
    "POSTGRES": ["postgresql-*.jar"],
    "SQLITE":   ["sqlite-jdbc-*.jar"],
    # ORACLE, MSSQL, etc. are not bundled today — _find_bundled_driver_jar()
    # simply returns None for these and the user must supply their own JAR
    # under the project directory, same as outside Docker.
}


def _find_bundled_driver_jar(db_type: str):
    """Look for a JDBC driver JAR bundled with the Gilhari/JDX SDK image.

    Returns the in-container path to the newest-looking match, or None if
    db_type isn't one of the bundled drivers (or external_libs/ isn't found —
    e.g. when not actually running inside the orm_skyway container).
    """
    if not db_type:
        return None
    patterns = _BUNDLED_DRIVER_PATTERNS.get(db_type.upper())
    if not patterns:
        return None
    ext_libs = Path(_DOCKER_JX_HOME) / "external_libs"
    if not ext_libs.is_dir():
        return None
    for pattern in patterns:
        matches = sorted(ext_libs.glob(pattern))
        if matches:
            return str(matches[-1])  # last = highest version, for simple semver-ish names
    return None


def yn_confirm(prompt: str, default: bool = True) -> bool:
    """ask_yn wrapper that auto-accepts when --yes is set."""
    if _YES:
        verbose_info(f"--yes: auto-accepting '{prompt}'")
        return default
    return ask_yn(prompt, default)


def pkg_to_rel(package: str):
    """Convert a dotted package name to a relative Path.
    Returns Path(".") for a blank package (no package = src/ and bin/ root).
    """
    if not package or not package.strip():
        return Path(".")
    return Path(*package.split("."))


def verbose_info(msg):
    """Print only when verbose mode is enabled."""
    if _VERBOSE:
        info(msg)


# ==============================================================================
# 1.  LOAD JSON CONFIG FILE
# ==============================================================================

def load_config_file(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        error(f"Config file not found: {path}")
        sys.exit(1)
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in config file: {e}")
        sys.exit(1)
    info(f"Loaded config file: {cfg_path.resolve()}")
    return data


# ==============================================================================
# 2.  COLLECT INPUTS
# ==============================================================================

def collect_inputs(args, phase: str = "1+3") -> dict:
    """Return a config dict, filling gaps with interactive prompts.

    phase controls which prompts are shown:
      "1" or "1+3" -- full prompts (DB connection, JDX home, project settings)
      "3"          -- only prompts needed to package the Docker image
                      (JDBC URL for .docker.jdx, driver info, package, Docker settings)
    """
    cfg = {}
    phase1_needed = phase in ("1", "1+3")

    # ── Step 1: Database Connection ───────────────────────────────────────────
    # JDBC URL is needed in both phases (Phase 3 uses it to generate .docker.jdx).
    # DB credentials and schema are only needed in Phase 1 (live DB connection).
    header("Phase 1 - Step 1 - Database Connection Information")

    if args.jdbc_url:
        cfg["jdbc_url"] = args.jdbc_url
    else:
        while True:
            cfg["jdbc_url"] = ask("JDBC URL (e.g. jdbc:mysql://localhost:3306/mydb)") or ""
            if cfg["jdbc_url"]:
                break
            error("JDBC URL is required. Please enter a value.")

    # Preserve the as-configured (host-side) JDBC URL before any Docker-mode
    # rewrite below. config/*.config, *.revjdx, and *.jdx are meant to remain
    # usable directly on the host (most importantly for JDXDemo, which can't
    # run inside the orm_skyway container at all — see host_jx_home). Those
    # files get reverted back to this value after generation, below.
    cfg["host_jdbc_url"] = cfg["jdbc_url"]

    # FA1: orm_skyway.py running inside the softwaretree/orm_skyway container.
    # "localhost" in the config means "the Docker host", not this container —
    # rewrite it transparently so Phase 1's live DB connection succeeds.
    # orm_skyway_config.json is left untouched; only the in-memory URL changes.
    if _running_in_docker():
        _container_safe_url = _docker_safe_jdbc_url(cfg["jdbc_url"])
        if _container_safe_url != cfg["jdbc_url"]:
            verbose_info(
                "Detected running inside a Docker container — using "
                f"host.docker.internal for the database connection "
                f"({cfg['jdbc_url']} -> {_container_safe_url})."
            )
            cfg["jdbc_url"] = _container_safe_url

    if phase1_needed:
        # Accept empty string from config as a valid value (means "no schema / default").
        # Only prompt if the value was never supplied (None = not in config or CLI).
        if args.db_schema is not None:
            cfg["db_schema"] = args.db_schema  # may be "" — that is valid
        elif _YES:
            cfg["db_schema"] = ""  # --yes: default to blank (no schema)
            verbose_info("--yes: db_schema defaulting to blank (no schema)")
        else:
            cfg["db_schema"] = ask("DB schema/catalog to inspect (blank = default)", "") or ""
    else:
        cfg["db_schema"] = getattr(args, "db_schema", None) or ""

    # Docker variant of JDBC URL: replace localhost/127.0.0.1 with
    # host.docker.internal so the container can reach the host DB.
    # SQLite and other file-based DBs are unaffected (no host to replace).
    # (No-op here when _running_in_docker() already rewrote cfg["jdbc_url"] above.)
    cfg["docker_jdbc_url"] = _docker_safe_jdbc_url(cfg["jdbc_url"])
    if cfg["docker_jdbc_url"] != cfg["jdbc_url"]:
        verbose_info(f"Docker JDBC URL (for .jdx inside image): {cfg['docker_jdbc_url']}")

    # Derive DB type from JDBC URL
    # Derive url_db_type from the JDBC URL — used for all script-internal routing:
    # H2 schema logic, getTables catalog/schema params, _METADATA_JDX lookup.
    # This is independent of what the user specifies for db_type.
    url_lower = cfg["jdbc_url"].lower()
    if   "mysql"     in url_lower: cfg["url_db_type"] = "MYSQL"
    elif "postgres"  in url_lower: cfg["url_db_type"] = "POSTGRES"
    elif "sqlserver" in url_lower or "mssql" in url_lower:
                                    cfg["url_db_type"] = "MSSQL"
    elif "oracle"    in url_lower: cfg["url_db_type"] = "ORACLE"
    elif "sqlite"    in url_lower: cfg["url_db_type"] = "SQLITE"
    elif "db2"       in url_lower: cfg["url_db_type"] = "DB2"
    elif "snowflake" in url_lower: cfg["url_db_type"] = "SNOWFLAKE"
    elif "mariadb"   in url_lower: cfg["url_db_type"] = "MARIADB"
    elif "databricks"in url_lower: cfg["url_db_type"] = "DATABRICKS"
    elif "jdbc:sap:"  in url_lower: cfg["url_db_type"] = "SAPHANA"
    elif "cloudspanner" in url_lower and "dialect=postgresql" in url_lower:
                                   cfg["url_db_type"] = "SPANNER"
    elif "cloudspanner" in url_lower: cfg["url_db_type"] = "CLOUDSPANNER"
    elif "cockroachdb" in url_lower or "cockroach" in url_lower:
                                   cfg["url_db_type"] = "COCKROACHDB"
    elif "yugabyte"  in url_lower: cfg["url_db_type"] = "YUGABYTE"
    elif "jdbc:excel:" in url_lower:
                                   cfg["url_db_type"] = "EXCEL"
    else:                          cfg["url_db_type"] = ""

    # db_type: used only for JDX_DBTYPE= in the generated config.
    # If explicitly set in config file or via --db-type, pass through verbatim
    # to JDX — JDX supports more DB type tokens than the script recognises
    # (e.g. ORACLE9, GENERIC) and will surface any invalid value immediately.
    # If not set, default to url_db_type.
    _explicit_db_type = (getattr(args, "db_type", None) or "").strip().upper()
    if _explicit_db_type:
        cfg["db_type"] = _explicit_db_type
        verbose_info(f"JDX_DBTYPE explicitly set to: {cfg['db_type']}")
    elif cfg["url_db_type"] == "EXCEL":
        # EXPERIMENTAL (2026-07-12): default JDX_DBTYPE to MSACCESS rather than
        # EXCEL for CData's Excel driver. MS Access and Excel both go through
        # JDX's Jet/ACE-family DDL handling, and jdxMetadata_Access.jdx (which
        # uses LONGTEXT for jdxMetaInfo) is confirmed to exist for MSACCESS —
        # trying it here to see whether it avoids the DROP TABLE issue seen
        # with the generic Excel path. Override with --db-type EXCEL (or
        # anything else) if this doesn't pan out.
        cfg["db_type"] = "MSACCESS"
        verbose_info("JDX_DBTYPE defaulted to MSACCESS for Excel (experimental — "
                     "override with --db-type if this doesn't resolve cleanly).")
    elif cfg["url_db_type"]:
        cfg["db_type"] = cfg["url_db_type"]
    else:
        cfg["db_type"] = (
            ask("JDX_DBTYPE for generated config (e.g. MYSQL/POSTGRES/ORACLE/MARIADB/DATABRICKS/GENERIC)", "GENERIC")
        ).upper()

    # ── H2: effective_schema and effective_jdbc_url resolution ──────────────────
    # Resolves the schema used for table discovery and JDX metadata creation so it
    # is always consistent with the runtime connection.  Sets two derived keys:
    #   cfg["effective_schema"]   — passed to getTables() for scoped discovery
    #   cfg["effective_jdbc_url"] — written into .config/.jdx/.docker.jdx
    #
    # Postgres cases:
    #  1. db_schema blank + no currentSchema= in URL  -> default to "public"
    #  2. db_schema blank + currentSchema= in URL     -> extract as effective_schema
    #  3. db_schema set  + currentSchema= absent      -> inject ?currentSchema= into
    #                                                    effective_jdbc_url
    #  4. db_schema set  + currentSchema= present + matching -> use as-is
    #  5. db_schema set  + currentSchema= present + differing -> error
    #
    # MySQL:
    #  db_schema blank -> extract database name from JDBC URL path segment
    #  db_schema set   -> use as-is (effective_schema = db_schema)
    #
    # All other DB types: effective_schema = db_schema, effective_jdbc_url = jdbc_url.
    import re as _re
    cfg["effective_schema"]   = cfg["db_schema"]
    cfg["effective_jdbc_url"] = cfg["jdbc_url"]
    if cfg.get("url_db_type") == "POSTGRES":
        _url_schema_match = _re.search(
            r'[?&]currentSchema=([^&]+)', cfg["jdbc_url"], _re.IGNORECASE)
        _url_schema = _url_schema_match.group(1) if _url_schema_match else ""
        _db_schema  = cfg["db_schema"]
        if not _db_schema and _url_schema:
            # Case 2: extract currentSchema= from URL
            cfg["effective_schema"] = _url_schema
            verbose_info(f"Postgres: effective_schema extracted from URL currentSchema=: {_url_schema}")
        elif _db_schema and not _url_schema:
            # Case 3: inject currentSchema= into effective_jdbc_url
            _sep = "&" if "?" in cfg["jdbc_url"] else "?"
            cfg["effective_jdbc_url"] = f'{cfg["jdbc_url"]}{_sep}currentSchema={_db_schema}'
            verbose_info(f"Postgres: injected currentSchema={_db_schema} into JDBC URL for generated ORM files")
        elif _db_schema and _url_schema:
            # Case 4: both present — must match
            if _db_schema.lower() != _url_schema.lower():
                error(f"Postgres schema mismatch: db_schema='{_db_schema}' differs from "
                      f"currentSchema='{_url_schema}' in the JDBC URL.")
                error("These must match. Either align them or remove one.")
                sys.exit(1)
            cfg["effective_schema"] = _db_schema
            verbose_info(f"Postgres: db_schema and currentSchema= both set to '{_db_schema}' — consistent")
        else:
            # Case 1: both blank — default to public (Postgres default search path).
            # Scoping to a single schema avoids multi-schema JDXMetadata ambiguity
            # and keeps the object model focused on one domain.
            # If your tables are in a different schema, set db_schema explicitly.
            _default_schema = "public"
            cfg["effective_schema"] = _default_schema
            _sep = "&" if "?" in cfg["jdbc_url"] else "?"
            cfg["effective_jdbc_url"] = f'{cfg["jdbc_url"]}{_sep}currentSchema={_default_schema}'
            info(f"Postgres: db_schema not set — defaulting to 'public' schema. "
                 f"Set db_schema explicitly to target a different schema.")

    elif cfg.get("url_db_type") == "MYSQL":
        # For MySQL, the database name and schema are the same concept.
        # Extract the database name from the JDBC URL path segment for comparison.
        # Without scoping to a single database, getTables(catalog=null, ...) scans
        # all databases on the server and returns duplicate table names.
        _mysql_db_match = _re.search(r'/([^/?]+)(?:\?|$)', cfg["jdbc_url"])
        _mysql_db = _mysql_db_match.group(1) if _mysql_db_match else ""
        if not cfg["db_schema"]:
            # db_schema blank — auto-extract from URL
            if _mysql_db:
                cfg["effective_schema"] = _mysql_db
                info(f"MySQL: db_schema not set — defaulting to database name "
                     f"'{_mysql_db}' from JDBC URL. "
                     f"Set db_schema explicitly to override.")
            else:
                warn("MySQL: could not extract database name from JDBC URL. "
                     "Table discovery will scan all databases. "
                     "Set db_schema to the database name to avoid this.")
        else:
            # db_schema explicitly set — must match the database name in the URL.
            # In MySQL, database name and schema name are the same concept, so
            # a mismatch means the user has specified conflicting settings.
            if _mysql_db and _mysql_db.lower() != cfg["db_schema"].lower():
                error(f"MySQL schema mismatch: db_schema='{cfg['db_schema']}' "
                      f"differs from database name '{_mysql_db}' in the JDBC URL.")
                error("These must match. Set db_schema to match the database name "
                      "in jdbc_url, or leave db_schema blank for auto-detection.")
                sys.exit(1)
            cfg["effective_schema"] = cfg["db_schema"]

    elif cfg.get("url_db_type") == "SNOWFLAKE":
        # Snowflake uses schema= as a URL parameter (e.g. ?schema=myschema).
        # Extract it when db_schema is blank; check for mismatch when both set.
        _sf_schema_match = _re.search(
            r'[?&]schema=([^&]+)', cfg["jdbc_url"], _re.IGNORECASE)
        _sf_schema = _sf_schema_match.group(1) if _sf_schema_match else ""
        _db_schema = cfg["db_schema"]
        if not _db_schema and _sf_schema:
            cfg["effective_schema"] = _sf_schema
            verbose_info(f"Snowflake: effective_schema extracted from URL schema=: {_sf_schema}")
        elif _db_schema and _sf_schema:
            if _db_schema.lower() != _sf_schema.lower():
                error(f"Snowflake schema mismatch: db_schema='{_db_schema}' differs from "
                      f"schema='{_sf_schema}' in the JDBC URL.")
                error("These must match. Either align them or remove one.")
                sys.exit(1)
            cfg["effective_schema"] = _db_schema
            verbose_info(f"Snowflake: db_schema and URL schema= both set to '{_db_schema}' — consistent")
        elif _db_schema:
            cfg["effective_schema"] = _db_schema
        # both blank — no default imposed for Snowflake

    # FA1: host_effective_jdbc_url mirrors effective_jdbc_url but built from
    # host_jdbc_url instead of the (possibly Docker-rewritten) jdbc_url.
    # effective_jdbc_url is always constructed as jdbc_url + an optional
    # suffix (e.g. "?currentSchema=public") above, so the same suffix applies
    # unchanged to host_jdbc_url — no need to duplicate the schema-resolution
    # branches themselves. Used after generation to restore config/*.config,
    # *.revjdx, and *.jdx back to a host-usable URL (see copy_revjdx_to_jdx
    # call site in run_phase1) since those files must keep working directly
    # on the host (JDXDemo can't run inside the orm_skyway container at all).
    _effective_suffix = cfg["effective_jdbc_url"][len(cfg["jdbc_url"]):]
    cfg["host_effective_jdbc_url"] = cfg["host_jdbc_url"] + _effective_suffix

    # Collect credentials — required for server-based DBs, optional for file-based ones.
    # SQLite does not use credentials; other DB types always require them.
    # A value from the config file or CLI flag is only accepted if it is non-empty;
    # an empty string in the config file is treated the same as a missing value.
    _creds_required = cfg["url_db_type"] != "SQLITE"
    if phase1_needed:
        # args.db_user is None when not in config/CLI; "" means explicitly set to blank.
        # In --yes mode or when creds not required, accept "" without prompting.
        if args.db_user is not None:
            cfg["db_user"] = args.db_user
            # For server DBs, blank credentials in config are an error in --yes mode
            if _YES and not cfg["db_user"] and _creds_required:
                error("--yes mode: db_user is required for this database type but is blank in config.")
                error("  Set db_user in the config file or via --db-user.")
                sys.exit(1)
        elif not _creds_required:
            cfg["db_user"] = ""  # SQLite — no credentials needed
        elif _YES:
            error("--yes mode: db_user is required for this database type but is not set in config.")
            error("  Set db_user in the config file or via --db-user.")
            sys.exit(1)
        else:
            while True:
                cfg["db_user"] = ask("DB username", "")
                if cfg["db_user"]:
                    break
                error("DB username is required for this database type. Please enter a value.")

        if args.db_password is not None:
            cfg["db_password"] = args.db_password
            if _YES and not cfg["db_password"] and _creds_required:
                error("--yes mode: db_password is required for this database type but is blank in config.")
                error("  Set db_password in the config file or via --db-password.")
                sys.exit(1)
        elif not _creds_required:
            cfg["db_password"] = ""  # SQLite — no credentials needed
        elif _YES:
            error("--yes mode: db_password is required for this database type but is not set in config.")
            error("  Set db_password in the config file or via --db-password.")
            sys.exit(1)
        else:
            while True:
                cfg["db_password"] = ask("DB password", "")
                if cfg["db_password"]:
                    break
                error("DB password is required for this database type. Please enter a value.")
    else:
        cfg["db_user"]     = getattr(args, "db_user",     None) or ""
        cfg["db_password"] = getattr(args, "db_password", None) or ""

    _default_drivers = {
        "MYSQL":      "com.mysql.cj.jdbc.Driver",
        "POSTGRES":   "org.postgresql.Driver",
        "ORACLE":     "oracle.jdbc.driver.OracleDriver",
        "MSSQL":      "com.microsoft.sqlserver.jdbc.SQLServerDriver",
        "SQLITE":     "org.sqlite.JDBC",
        "DB2":        "com.ibm.db2.jcc.DB2Driver",
        "SNOWFLAKE":   "net.snowflake.client.api.driver.SnowflakeDriver",
        "MARIADB":     "org.mariadb.jdbc.Driver",
        "DATABRICKS":  "com.databricks.client.jdbc.Driver",
        "SPANNER":     "com.google.cloud.spanner.jdbc.JdbcDriver",
        "CLOUDSPANNER":"com.google.cloud.spanner.jdbc.JdbcDriver",
        "COCKROACHDB": "org.postgresql.Driver",
        "YUGABYTE":    "org.postgresql.Driver",
    }
    _default_class = _default_drivers.get(cfg["db_type"], "")
    if args.jdbc_driver_class:
        cfg["jdbc_driver_class"] = args.jdbc_driver_class
    else:
        while True:
            cfg["jdbc_driver_class"] = ask("JDBC driver class name", _default_class) or ""
            if cfg["jdbc_driver_class"]:
                break
            error("JDBC driver class name is required. Please enter a value.")

    if args.jdbc_driver_jar:
        cfg["jdbc_driver_jar"] = args.jdbc_driver_jar
    else:
        while True:
            cfg["jdbc_driver_jar"] = ask("Full path to JDBC driver JAR") or ""
            if cfg["jdbc_driver_jar"]:
                break
            error("JDBC driver JAR path is required. Please enter a value.")

    # Optional accompanying license file (e.g. CData drivers). No interactive
    # prompt — auto-detected later as a same-stem .lic sibling of the jar;
    # this only captures an explicit override via --jdbc-driver-lic / config.
    cfg["jdbc_driver_lic"] = (args.jdbc_driver_lic or "").strip()

    # Preserve the as-configured (host-side) driver-jar path before any
    # Docker-mode override below. setEnvironment.bat/.sh and JDXDemo.bat/.sh
    # need this value — they're meant to be runnable directly on the host
    # later (JDXDemo in particular requires Swing GUI, which can't run inside
    # the orm_skyway container), so baking in an in-container-only path would
    # silently break them. cfg["jdbc_driver_jar"] itself may still be
    # overridden below for *this process's own* in-container operations.
    cfg["host_jdbc_driver_jar"] = cfg["jdbc_driver_jar"]

    # FA1: running inside the softwaretree/orm_skyway container. A driver-jar
    # path that's already reachable here (e.g. a relative path under the
    # mounted /project directory, such as ./config/<driver>.jar — the
    # convention used in the Gilhari sample projects) is left untouched.
    # Otherwise — most commonly a host-only absolute path like
    # "C:/SoftwareTree/JDX5.x/external_libs/..." that doesn't exist inside the
    # container — fall back to the matching driver JAR already bundled with
    # the Gilhari/JDX SDK in this image, if there is one for this db_type.
    if _running_in_docker():
        _configured = cfg.get("jdbc_driver_jar", "")
        if _configured and Path(_configured).is_file():
            verbose_info(f"Using configured JDBC driver JAR (found under /project): {_configured}")
        else:
            _bundled = _find_bundled_driver_jar(cfg.get("db_type"))
            if _bundled:
                verbose_info(
                    "Detected running inside a Docker container — configured "
                    f"jdbc_driver_jar ({_configured!r}) isn't reachable here; "
                    f"using the bundled driver instead: {_bundled}"
                )
                cfg["jdbc_driver_jar"] = _bundled
            elif _configured:
                warn(
                    f"jdbc_driver_jar ({_configured}) was not found inside the container "
                    "and no bundled driver matches this database type. "
                    "Copy the driver JAR into your project directory (e.g. ./config/) "
                    "and reference it with a relative path."
                )

    # ── Optional: JDX dev bin path — prepended to classpath for SDK dev testing ─
    # Not prompted interactively — only picked up from config file or --jdx-dev-bin-path.
    cfg["jdx_dev_bin_path"] = (getattr(args, "jdx_dev_bin_path", None) or "").strip()
    if cfg["jdx_dev_bin_path"]:
        info(f"JDX dev bin path: {cfg['jdx_dev_bin_path']} (prepended to classpath)")

    # ── Step 2: JDX / Gilhari Installation (Phase 1 only) ────────────────────
    if phase1_needed:
        header("Phase 1 - Step 2 - JDX / Gilhari Installation")
        jx_home_env = os.environ.get("JX_HOME", "")
        if _running_in_docker():
            # Don't block on an interactive prompt for a value this process
            # itself won't use (live operations use the bundled SDK below
            # regardless). Best-effort host_jx_home from config/CLI/env only —
            # this is what setEnvironment.bat/.sh and JDXDemo.bat/.sh need,
            # since JDXDemo requires Swing GUI and can only run on the host,
            # not inside this container.
            cfg["host_jx_home"] = args.jx_home or jx_home_env or ""
            cfg["jx_home"] = _DOCKER_JX_HOME
            verbose_info(f"Running in Docker — using bundled JDX SDK at {_DOCKER_JX_HOME} for this run.")
            if not cfg["host_jx_home"]:
                info(
                    "No local JDX installation is configured for this project "
                    "(jx_home is blank). JDXDemo.bat/.sh cannot run inside this "
                    "container (Swing GUI needs a display), so they need a usable "
                    "JX_HOME on the host to run there instead."
                )
                if yn_confirm(
                    "Create a local JDX sandbox under jdx_sandbox/ in this project "
                    "(confirms you do not already have JDX installed on this host)?",
                    default=True,
                ):
                    _sandbox_host_jx_home = _create_jdx_sandbox(cfg)
                    if _sandbox_host_jx_home:
                        cfg["host_jx_home"] = _sandbox_host_jx_home
                if not cfg["host_jx_home"]:
                    warn(
                        "setEnvironment.bat/.sh will be written with an empty JX_HOME — "
                        "fill it in manually before running JDXDemo.bat/.sh outside the container."
                    )
        else:
            if args.jx_home:
                cfg["jx_home"] = args.jx_home
            else:
                while True:
                    cfg["jx_home"] = ask("JX_HOME (root of JDX or Gilhari installation)", jx_home_env) or ""
                    if cfg["jx_home"]:
                        break
                    error("JX_HOME is required. Please enter a value.")
            cfg["host_jx_home"] = cfg["jx_home"]
    else:
        cfg["jx_home"] = getattr(args, "jx_home", None) or os.environ.get("JX_HOME", "")
        cfg["host_jx_home"] = cfg["jx_home"]
        if _running_in_docker():
            cfg["jx_home"] = _DOCKER_JX_HOME

    # ── Step 3: Project Settings ──────────────────────────────────────────────
    header("Phase 1 - Step 3 - Project Settings")

    if args.object_model_package is not None:
        cfg["object_model_package"] = (args.object_model_package or "").strip()
    else:
        cfg["object_model_package"] = ask(
            "Java package for generated model classes (e.g. com.example.json.model, or blank for no package)",
            None
        ) or ""
    cfg["reverse_eng_template_config"] = (
        args.reverse_eng_template_config or
        ask("Base name for the reverse-engineering template config file", "reverse_eng_template")
    )

    if phase1_needed:
        cfg["model_overview"] = (
            getattr(args, "model_overview", None) or
            ask(
                "Object model overview (one-line description for AI/clients)",
                f"A {cfg.get('url_db_type', 'relational').lower()} database object model"
            )
        )
    else:
        cfg["model_overview"] = getattr(args, "model_overview", None) or ""

    # Docker / Gilhari settings (needed for both phases)
    # docker_image_name must be project-specific to avoid conflicts between
    # projects on the same machine. We require a non-empty value and do not
    # suggest a default — the user must choose a meaningful name.
    _supplied_image = (getattr(args, "docker_image_name", None) or "").strip()
    if _supplied_image:
        # Non-empty value supplied — confirm with the user
        info(f"Docker image name from config: {_supplied_image}")
        if yn_confirm(f"Use '{_supplied_image}' as the Docker image name?", default=True):
            cfg["docker_image_name"] = _supplied_image
        else:
            while True:
                cfg["docker_image_name"] = ask("Docker image / microservice name", None) or ""
                if cfg["docker_image_name"]:
                    break
                error("Docker image name is required. Please enter a value.")
    else:
        while True:
            cfg["docker_image_name"] = ask("Docker image / microservice name (e.g. my-sakila-service)", None) or ""
            if cfg["docker_image_name"]:
                break
            error("Docker image name is required. Please enter a value.")
    cfg["docker_image_tag"] = (
        getattr(args, "docker_image_tag", None) or
        ask("Docker image tag", "1.0")
    )
    # embed_db_file_in_microservice: only meaningful for file-based DBs
    cfg["embed_db_file_in_microservice"] = bool(
        getattr(args, "embed_db_file_in_microservice", False)
    )
    cfg["gilhari_host_port"] = int(
        getattr(args, "gilhari_host_port", None) or
        ask("Host port to expose Gilhari REST service on", "80")
    )
    # Docker target platform — auto-detected from host CPU architecture so
    # Apple Silicon (arm64) machines don't get an amd64-only image that fails
    # to start. CLI flag / config file value always wins if supplied.
    _supplied_platform = (getattr(args, "docker_platform", None) or "").strip()
    cfg["docker_platform"] = _supplied_platform or _detect_docker_platform()
    if _supplied_platform:
        verbose_info(f"Docker platform (from config/CLI): {cfg['docker_platform']}")
    else:
        verbose_info(f"Docker platform (auto-detected from host): {cfg['docker_platform']}")

    # Optional fixed MAC address for the container (node-locked JDBC driver
    # licenses, e.g. CData). No default — only passed to `docker run` if set.
    cfg["docker_mac_address"] = (getattr(args, "docker_mac_address", None) or "").strip()
    if cfg["docker_mac_address"]:
        verbose_info(f"Docker container MAC address (pinned): {cfg['docker_mac_address']}")

    # Optional fixed hostname for the container. Defaults to the image name
    # if unset — but for node-locked JDBC licensing (e.g. CData) that default
    # may not match what the license was actually issued/activated for.
    cfg["docker_hostname"] = (getattr(args, "docker_hostname", None) or "").strip()
    if cfg["docker_hostname"]:
        verbose_info(f"Docker container hostname (pinned): {cfg['docker_hostname']}")

    if cfg.get("url_db_type") == "EXCEL" and not (cfg["docker_mac_address"] and cfg["docker_hostname"]):
        warn("Excel/CData: confirmed (2026-07-14) that the CData driver's license check requires the "
             "container's hostname AND MAC address to match your ACTUAL HOST MACHINE'S real values — not "
             "just any fixed/consistent values. Set both explicitly before running Phase 3:")
        warn("  --docker-hostname <your machine's hostname>   (Windows: run `hostname` or check %COMPUTERNAME%)")
        warn("  --docker-mac-address <your machine's MAC>      (Windows: run `getmac /v`)")
        warn("...or re-run Phase 3 after setting docker_hostname/docker_mac_address in your config file.")

    # Project root is always the current working directory
    if getattr(args, "project_dir", None):
        cfg["project_root"] = Path(args.project_dir).resolve()
        if not cfg["project_root"].exists():
            error(f"Project directory not found: {cfg['project_root']}")
            sys.exit(1)
        info(f"Project root: {cfg['project_root']}")
    else:
        cfg["project_root"] = Path.cwd()
    verbose_info(f"Project root: {cfg['project_root']}")

    return cfg


# ==============================================================================
# 3.  LIST TABLES  (tiny Java helper compiled and run on the fly)
# ==============================================================================

LIST_TABLES_JAVA = """\
import java.sql.*;
import java.util.*;

public class ListTablesHelper {
    public static void main(String[] args) throws Exception {
        String url      = args[0];
        String user     = args[1];
        String password = args[2];
        String dbType   = args.length > 3 ? args[3].toUpperCase() : "";
        String schema   = args.length > 4 && !args[4].isEmpty() ? args[4] : null;

        // JDBC getTables(catalog, schemaPattern, ...) semantics vary by DB:
        //   MySQL:      catalog = database name, schemaPattern = null (ignored)
        //   PostgreSQL: catalog = null (ignored), schemaPattern = schema name
        //   Oracle:     catalog = null (ignored), schemaPattern = owner/schema
        //   MSSQL:      catalog = null, schemaPattern = schema name
        //   SQLite:     both null (no schema concept)
        String catalog;
        String schemaPattern;
        if (dbType.equals("MYSQL")) {
            catalog       = schema;  // MySQL uses catalog as the database/schema filter
            schemaPattern = null;
        } else {
            // POSTGRES, ORACLE, MSSQL, SQLITE, unknown
            catalog       = null;
            schemaPattern = schema;
        }

        // For MSSQL, prefix table names with schema so the user sees
        // schema.tableName in the selection menu and the config mapping
        // reflects the fully-qualified name used by JDX.
        boolean qualifyWithSchema = dbType.equals("MSSQL") && schema != null;

        Connection con = DriverManager.getConnection(url, user, password);
        DatabaseMetaData meta = con.getMetaData();
        ResultSet rs = meta.getTables(catalog, schemaPattern, "%",
                                      new String[]{"TABLE", "VIEW"});
        List<String> tables = new ArrayList<>();
        while (rs.next()) {
            String t = rs.getString("TABLE_NAME");
            if (t != null) {
                tables.add(qualifyWithSchema ? schema + "." + t : t);
            }
        }
        rs.close(); con.close();
        Collections.sort(tables);
        for (String t : tables) System.out.println(t);
    }
}
"""

def list_tables_via_java(cfg: dict) -> list:
    info("Connecting to database to retrieve table list ...")

    tmp = cfg["project_root"] / ".tmp_helper"
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        src = tmp / "ListTablesHelper.java"
        src.write_text(LIST_TABLES_JAVA, encoding="utf-8")

        driver_jar = cfg["jdbc_driver_jar"]
        cp = SEP.join([str(tmp), driver_jar])

        ret = subprocess.run(["javac", "-cp", cp, str(src)], capture_output=True, text=True)
        if ret.returncode != 0:
            error("Could not compile the JDBC helper class.")
            error(ret.stderr)
            sys.exit(1)

        # Pass db_type as arg 3 so ListTablesHelper can route catalog/schema
        # correctly per DB (MySQL uses catalog, Postgres/Oracle use schemaPattern).
        # Pass effective_schema as arg 4 — resolved in collect_inputs; for Postgres
        # this may be extracted from currentSchema= in the URL when db_schema is blank.
        cmd = ["java", "-cp", cp, "ListTablesHelper",
               cfg["jdbc_url"], cfg["db_user"], cfg["db_password"],
               cfg.get("url_db_type", "")]
        if cfg.get("effective_schema"):
            cmd.append(cfg["effective_schema"])

        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            error("Could not connect to the database or list tables.")
            error(ret.stderr)
            sys.exit(1)

        return [t.strip() for t in ret.stdout.strip().splitlines() if t.strip()]
    finally:
        # Always clean up the temporary helper directory regardless of outcome.
        # This keeps the project directory clean and makes the "no files were
        # written" message in --phase introspect accurate.
        if tmp.exists():
            shutil.rmtree(str(tmp))
            verbose_info("Cleaned up .tmp_helper/ directory.")




# ==============================================================================
# 3b. ENSURE JDXTestConnection TABLE EXISTS (pre-step before -metaForceCreate)
# ==============================================================================

CREATE_TEST_CONNECTION_JAVA = """\
import java.sql.*;

public class CreateTestConnectionHelper {
    public static void main(String[] args) throws Exception {
        String url    = args[0];
        String user   = args[1];
        String pass   = args[2];
        String dbType = args.length > 3 ? args[3].toUpperCase() : "";

        Connection con = DriverManager.getConnection(url, user, pass);
        // Pre-create JDXTestConnection to avoid a JDX bug on PostgreSQL where
        // a failed SELECT on a missing table leaves an aborted transaction open,
        // blocking the subsequent CREATE TABLE inside JDX.
        // MSSQL does not support CREATE TABLE IF NOT EXISTS — use a safe
        // existence check instead. All other DB types use the standard syntax.
        if (dbType.equals("MSSQL") || dbType.equals("HANA") || dbType.equals("SAPHANA")) {
            // SQL Server and SAP HANA do not support CREATE TABLE IF NOT EXISTS —
            // use a metadata existence check instead.
            java.sql.ResultSet rs = con.getMetaData().getTables(
                null, null, "JDXTestConnection", new String[]{"TABLE"});
            boolean exists = rs.next();
            rs.close();
            if (!exists) {
                con.createStatement().executeUpdate(
                    "CREATE TABLE JDXTestConnection (test INT)");
            }
        } else {
            con.createStatement().executeUpdate(
                "CREATE TABLE IF NOT EXISTS JDXTestConnection (test INT)");
        }
        con.close();
        System.out.println("JDXTestConnection ready.");
    }
}
"""


def ensure_jdxtestconnection(cfg: dict):
    """
    Pre-create JDXTestConnection table before invoking JDXSchema -metaForceCreate.

    JDX checks for this table on startup by running SELECT 1 FROM JDXTestConnection.
    If the table is absent, JDX catches the SQLException and tries to CREATE it —
    but on PostgreSQL the failed SELECT leaves an aborted transaction open, causing
    the subsequent CREATE TABLE to fail too.

    For most DB types, uses `CREATE TABLE IF NOT EXISTS` which is a silent no-op
    when the table already exists. For MSSQL, which does not support that syntax,
    uses a metadata existence check before creating.
    """
    tmp = cfg["project_root"] / ".tmp_helper"
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        src = tmp / "CreateTestConnectionHelper.java"
        src.write_text(CREATE_TEST_CONNECTION_JAVA, encoding="utf-8")

        driver_jar = cfg["jdbc_driver_jar"]
        cp = SEP.join([str(tmp), driver_jar])

        ret = subprocess.run(["javac", "-cp", cp, str(src)],
                             capture_output=True, text=True)
        if ret.returncode != 0:
            error("Could not compile the JDXTestConnection helper class.")
            error(ret.stderr)
            sys.exit(1)

        # Use effective_jdbc_url so Postgres currentSchema= is honoured
        _url = cfg.get("effective_jdbc_url") or cfg["jdbc_url"]
        cmd = ["java", "-cp", cp, "CreateTestConnectionHelper",
               _url, cfg["db_user"], cfg["db_password"],
               cfg.get("url_db_type", "")]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            error("Could not create JDXTestConnection table.")
            error(ret.stderr)
            sys.exit(1)
        verbose_info(ret.stdout.strip() if ret.stdout else "")
    finally:
        if tmp.exists():
            shutil.rmtree(str(tmp))
            verbose_info("Cleaned up .tmp_helper/ directory (JDXTestConnection step).")


# ==============================================================================
# 3c. ENSURE JDXMetadata TABLE EXISTS (via JDXSchema -metaForceCreate)
# ==============================================================================

# Map our db_type tokens to the SDK's per-DB metadata spec files.
# These files live in %JX_HOME%/config/ and contain the ORM mapping for
# the JDXMetadata and JDXSequence tables.
_METADATA_JDX = {
    "MYSQL":    "jdxMetadata_mysql.jdx",
    "POSTGRES": "jdxMetadata_postgres.jdx",
    "ORACLE":   "jdxMetadata_ora.jdx",
    "MSSQL":    "jdxMetadata.jdx",
    "SQLITE":   "jdxMetadata.jdx",
    "DB2":      "jdxMetadata_db2.jdx",
    "SNOWFLAKE":"jdxMetadata.jdx",
    "MARIADB":  "jdxMetadata_mysql.jdx",   # MySQL-compatible
    "DATABRICKS":"jdxMetadata.jdx",
    "SPANNER":  "jdxMetadata_postgres.jdx", # PostgreSQL-compatible
    "CLOUDSPANNER":"jdxMetadata.jdx",        # reserved for future
    "COCKROACHDB":"jdxMetadata_postgres.jdx",# PostgreSQL-compatible
    "YUGABYTE": "jdxMetadata_postgres.jdx",  # PostgreSQL-compatible
    "HANA":     "jdxMetadata_saphana.jdx",   # SAP HANA — uses CLOB for jdxMetaInfo (HANA JDBC rejects "text")
    "SAPHANA":  "jdxMetadata_saphana.jdx",   # SAP HANA alias
    "EXCEL":    "jdxMetadata_Access.jdx",    # EXPERIMENTAL (2026-07-12): CData Excel driver, via JDX_DBTYPE=MSACCESS.
                                              # Uses LONGTEXT for jdxMetaInfo. Testing whether this avoids the
                                              # DROP TABLE issue seen with the generic Excel/jdxMetadata.jdx path.
    "MSACCESS": "jdxMetadata_Access.jdx",    # MS Access proper, same template
    "GENERIC":  "jdxMetadata.jdx",           # generic/unknown databases
}


def ensure_jdxmetadata_via_jdxschema(cfg: dict, jdx_path: Path, all_tables: list):
    """
    Create JDXMetadata (and JDXSequence) tables if not already present,
    using JDXSchema -metaForceCreate with the project .jdx file.

    Must be called AFTER compile_classes() — JDXSchema validates the mapping
    file on startup and requires the model .class files to be present in bin/.
    If --skip-compile was set and .class files are absent, JDXSchema will
    report an error at runtime; that error is surfaced and the script exits.

    -metaForceCreate drops and recreates JDXMetadata and JDXSequence, so any
    stale JDXSequence table is cleaned up automatically.
    -IGNORE_WARNINGS suppresses warnings when JDXSequence does not exist yet.

    JDX_METADATA_FILE is already written into the .config (and therefore
    propagated to .revjdx, .jdx, .docker.jdx) by generate_template_config,
    so no injection is needed here.
    """
    header("Phase 1 - Step 12 - Check JDXMetadata Table")
    if any(t.upper() == "JDXMETADATA" for t in all_tables):
        info("JDXMetadata table already present in the database — skipping metaCreate.")
        return

    info("JDXMetadata table not found in the database.")
    info("Creating JDXMetadata table to protect existing data in the reverse-engineered tables...")

    root       = cfg["project_root"]
    jx_home    = cfg["jx_home"]
    driver_jar = cfg["jdbc_driver_jar"]

    cp = _build_cp(cfg,
        str(root / BIN_DIR),
        str(root / CONFIG_DIR),
        str(Path(jx_home) / "libs" / "jxclasses.jar"),
        str(Path(jx_home) / "libs" / "jdxtools.jar"),
        str(Path(jx_home) / "external_libs" / "json-20240303.jar"),
        driver_jar,
        ".",
    )

    cmd = [
        "java",
        f"-DJX_HOME={jx_home}",
        "-cp", cp,
        "com.softwaretree.jdxtools.JDXSchema",
        "-metaForceCreate",
        "-IGNORE_WARNINGS",
        str(jdx_path.resolve()),
    ]
    verbose_info(f"Command: {' '.join(cmd)}")
    # Show JDXSchema output in verbose mode; always capture to check for errors
    ret = subprocess.run(cmd, cwd=str(root), text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    verbose_info(ret.stdout.strip() if ret.stdout else "")
    # H12: JDXSchema may exit 0 even on fatal errors — check output too
    _jdx_failed = (ret.returncode != 0 or
                   (ret.stdout and ": Exception:" in ret.stdout))
    if _jdx_failed:
        _surface_jdx_error(
            ret.stdout or "",
            "JDXSchema -metaForceCreate failed."
        )
        sys.exit(1)
    info("JDXMetadata table created successfully.")


# ==============================================================================
# 4.  INTERACTIVE TABLE SELECTION
# ==============================================================================

def select_tables(all_tables: list) -> list:

    # Match case-insensitively — some databases (e.g. MySQL) return
    # table names in lowercase even when created with mixed case.
    JDX_INTERNAL = {"jdxmetadata", "jdxsequence", "jdxtestconnection"}
    # Strip schema prefix (e.g. "SalesLT.JDXMetadata" -> "jdxmetadata") before
    # comparing so schema-qualified names are correctly excluded.
    def _bare(name): return name.split(".")[-1].lower()
    filtered = [t for t in all_tables if _bare(t) not in JDX_INTERNAL]
    hidden   = [t for t in all_tables if _bare(t) in JDX_INTERNAL]
    if hidden:
        info(f"Auto-excluding JDX internal tables: {', '.join(hidden)}")

    # In --yes mode, error immediately before showing the table list —
    # displaying tables and then erroring is confusing.
    if _YES:
        error("--yes mode requires 'tables' to be set in the config file or via --tables.")
        error("  Set 'tables' to a comma-separated list of table names, or 'all' to select every table.")
        error("  Tip: run with --phase introspect to see all available table names.")
        sys.exit(1)

    if HAS_RICH:
        tbl = Table(title="Available Tables", show_lines=True)
        tbl.add_column("#", style="cyan", justify="right")
        tbl.add_column("Table Name", style="white")
        for i, t in enumerate(filtered, 1):
            tbl.add_row(str(i), t)
        console.print(tbl)
    else:
        print("\nAvailable tables:")
        for i, t in enumerate(filtered, 1):
            print(f"  {i:3}. {t}")

    print()
    print("Enter table numbers separated by commas/spaces,")
    print("ranges like 1-3, 'all' for every table, or table names directly.")
    selection_raw = ask("Your selection")

    if selection_raw.strip().lower() == "all":
        return list(filtered)

    selected = []
    for tok in selection_raw.replace(",", " ").split():
        tok = tok.strip()
        if not tok:
            continue
        # Range e.g. "1-3"
        if "-" in tok:
            parts = tok.split("-")
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                lo, hi = int(parts[0]), int(parts[1])
                for idx in range(lo, hi + 1):
                    if 1 <= idx <= len(filtered):
                        selected.append(filtered[idx - 1])
                    else:
                        warn(f"Index {idx} out of range (1-{len(filtered)}); skipping.")
                continue
        # Single number
        if tok.isdigit():
            idx = int(tok)
            if 1 <= idx <= len(filtered):
                selected.append(filtered[idx - 1])
            else:
                warn(f"Index {idx} out of range (1-{len(filtered)}); skipping.")
        else:
            # Literal table name
            if tok in filtered:
                selected.append(tok)
            else:
                warn(f"Table '{tok}' not found; skipping.")

    # Deduplicate, preserve order
    seen, result = set(), []
    for t in selected:
        if t not in seen:
            seen.add(t)
            result.append(t)

    if not result:
        error("No valid tables selected. Aborting.")
        sys.exit(1)

    info(f"Selected {len(result)} table(s): {', '.join(result)}")
    return result


# ==============================================================================
# 5.  GENERATE TEMPLATE CONFIG
# ==============================================================================

def to_class_name(table_name: str) -> str:
    """snake_case / mixed -> PascalCase Java class name.
    Strips schema prefix (e.g. "SalesLT.Address" -> "Address") before
    converting so the class name never includes the schema.
    """
    bare = table_name.split(".")[-1]  # strip schema prefix if present
    return "".join(part.capitalize() for part in bare.split("_"))


def review_class_names(selected_tables: list) -> dict:
    """
    Show a table of Table -> Class Name pairs and let the user rename any
    class before the template config is written.
    Returns an ordered dict: {table_name: class_name}
    """
    header("Phase 1 - Step 6 - Review / Rename Class Names")

    # Build initial mapping (default = PascalCase of table name)
    mapping = {t: to_class_name(t) for t in selected_tables}

    if HAS_RICH:
        tbl = Table(title="Table -> Class Name Mapping  (edit class names as desired)",
                    show_lines=True)
        tbl.add_column("#",          style="cyan",  justify="right")
        tbl.add_column("Table Name", style="white")
        tbl.add_column("Class Name", style="green")
        for i, (table, cls) in enumerate(mapping.items(), 1):
            tbl.add_row(str(i), table, cls)
        console.print(tbl)
    else:
        print()
        print(f"  {'#':>3}  {'Table Name':<30}  Class Name")
        print(f"  {'─'*3}  {'─'*30}  {'─'*30}")
        for i, (table, cls) in enumerate(mapping.items(), 1):
            print(f"  {i:>3}  {table:<30}  {cls}")

    print()
    if _YES:
        verbose_info("--yes: skipping class rename review, using default PascalCase names")
        return mapping
    print("To rename a class, enter its number followed by the new name.")
    print("Example:  2 Employee     (renames class #2 to Employee)")
    print("Press Enter with no input when done.")

    while True:
        raw = ask("Rename [number name] or Enter to continue", "").strip()
        if not raw:
            break
        parts = raw.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            warn("Format: <number> <NewClassName>  e.g.  3 Employee")
            continue
        idx = int(parts[0])
        tables = list(mapping.keys())
        if not (1 <= idx <= len(tables)):
            warn(f"Number must be between 1 and {len(tables)}.")
            continue
        new_name = parts[1].strip()
        if not new_name.isidentifier():
            warn(f"'{new_name}' is not a valid Java identifier.")
            continue
        table = tables[idx - 1]
        old_name = mapping[table]
        mapping[table] = new_name
        verbose_info(f"  {table}  ->  {new_name}  (was {old_name})")

    # Show final mapping
    if HAS_RICH:
        tbl = Table(title="Final Table -> Class Name Mapping", show_lines=True)
        tbl.add_column("Table Name", style="white")
        tbl.add_column("Class Name", style="green")
        for table, cls in mapping.items():
            tbl.add_row(table, cls)
        console.print(tbl)
    else:
        print()
        print("  Final mapping:")
        for table, cls in mapping.items():
            print(f"    {table:<30}  {cls}")

    return mapping


def generate_template_config(cfg: dict, table_class_map: dict) -> Path:
    """
    table_class_map: ordered dict of {table_name: class_name}
    """
    import datetime
    header("Phase 1 - Step 7 - Generate JDX Template Config")

    root       = cfg["project_root"]
    config_dir = root / CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / f"{cfg['reverse_eng_template_config']}.config"

    # Collision check
    existing = [f for f in root.rglob("*")
                if f.is_file() and ".tmp_helper" not in str(f)]
    if existing:
        verbose_info(f"Project directory already contains {len(existing)} file(s).")
        if config_path.exists():
            verbose_info(f"Config file already exists: {config_path.relative_to(root)}")
        print("  [O] Overwrite  - replace config and scripts (other files untouched)")
        print("  [B] Backup     - rename existing config to .bak first")
        print("  [A] Abort      - exit without changing anything")
        if _YES:
            verbose_info("--yes: auto-accepting Overwrite")
            choice = "O"
        else:
            while True:
                choice = ask("Your choice [O/B/A]", "O").strip().upper()
                if choice in ("O", "B", "A"):
                    break
                warn("Please enter O, B, or A.")
        if choice == "A":
            info("Aborted by user.")
            sys.exit(0)
        if choice == "B" and config_path.exists():
            backup = config_path.with_suffix(".config.bak")
            config_path.rename(backup)
            info(f"Existing config backed up to: {backup.relative_to(root)}")

    # Build JDX_DATABASE line.
    # JDX requires non-empty USER and PASSWORD values in the connection string.
    # For databases that don't use credentials (e.g. SQLite), use placeholders
    # so the JDX parser does not fail on empty values.
    jdx_user     = cfg['db_user']     or 'noName'
    jdx_password = cfg['db_password'] or 'noPassword'
    # Use effective_jdbc_url — for Postgres with db_schema set but no currentSchema=
    # in the original URL, this carries the injected ?currentSchema= parameter so
    # the JDX runtime resolves tables in the correct schema.
    _jdx_url = cfg.get("effective_jdbc_url") or cfg["jdbc_url"]

    # Excel (CData JDBC driver): default to ReadOnly=True unless the user has
    # already specified ReadOnly= explicitly. Without this, JDX's schema
    # initialization (JDXSchema -metaForceCreate, triggered whenever it
    # doesn't find a JDXMetadata table/sheet) will attempt DROP TABLE /
    # CREATE TABLE against the live Excel sheet — DROP succeeds and destroys
    # the sheet's data, then CREATE fails because the generated SQL isn't
    # compatible with the CData driver. ReadOnly=True makes the driver reject
    # those statements outright instead of executing the destructive half.
    if cfg.get("url_db_type") == "EXCEL" and "readonly=" not in _jdx_url.lower():
        _sep = "&" if "?" in _jdx_url and ";" not in _jdx_url else ";"
        _jdx_url = _jdx_url.rstrip(";") + f"{_sep}ReadOnly=True"
        verbose_info("Excel/CData JDBC URL: added ReadOnly=True by default "
                     "(prevents JDX schema-init from DROP/CREATE-ing the sheet; "
                     "set ReadOnly=False explicitly in jdbc_url if you need write access).")

    jdx_db_line = (
        f"JDX_DATABASE JDX:{_jdx_url};"
        f"USER={jdx_user};PASSWORD={jdx_password};"
        f"JDX_DBTYPE={cfg['db_type']};DEBUG_LEVEL=5"
    )

    # JDXSchema writes .java files to JDX_OUTPUT_DIRECTORY (relative to cwd)
    # When package is blank, files go directly into src/
    package     = cfg["object_model_package"]
    pkg_path    = "/".join(package.split(".")) if package else ""
    src_out_dir = f"./{SRC_DIR}/{pkg_path}" if pkg_path else f"./{SRC_DIR}"

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "// JDX Reverse Engineering Template",
        f"// Generated by orm_skyway.py  [{timestamp}]",
        "",
        jdx_db_line,
        f"JDBC_DRIVER {cfg['jdbc_driver_class']}",
        f"JDX_OUTPUT_DIRECTORY {src_out_dir}",
        # Omit JDX_OBJECT_MODEL_PACKAGE entirely when no package is specified
        *([f"JDX_OBJECT_MODEL_PACKAGE {cfg['object_model_package']}"] if cfg['object_model_package'] else []),
        f"JDX_METADATA_FILE {_METADATA_JDX.get(cfg.get('url_db_type', ''), 'jdxMetadata.jdx')}",
        "JDX_SUPERCLASS_NAME com.softwaretree.jdx.JDX_JSONObject",
        "JDX_GENERATE_ACCESSOR_METHODS FALSE",
        "JDX_GENERATE_JSON_MAPPINGS TRUE",
        f"OBJECT_MODEL_OVERVIEW {cfg['model_overview']}",
        ";",
        "// Table -> Class mappings",
    ]
    # For MSSQL, table names in the CLASS mapping are already schema-qualified
    # (e.g. SalesLT.CustomerAddress) because ListTablesHelper returns them that
    # way when effective_schema is set. No additional prefix needed here.
    for table, class_name in table_class_map.items():
        lines.append(f"CLASS {class_name} TABLE {table}")
        lines.append(";")

    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    info(f"Template config written to: {config_path.relative_to(root)}")
    return config_path


# ==============================================================================
# 6.  WRITE HELPER SCRIPTS
# ==============================================================================

def _build_cp(cfg: dict, *parts) -> str:
    """Build a classpath string, optionally prepending jdx_dev_bin_path.
    parts: classpath entries in order (after the dev bin path).
    """
    dev = cfg.get("jdx_dev_bin_path", "").strip()
    entries = ([dev] if dev else []) + list(parts)
    return SEP.join(entries)


def write_helper_scripts(cfg: dict, config_path: Path, selected_tables: list):
    root       = cfg["project_root"]
    # These generated scripts (setEnvironment, JDXReverseEngineer, compile,
    # JDXDemo) are standalone artifacts meant to be run later directly on the
    # host's own JDK/JDX install — most notably JDXDemo, which needs Swing
    # GUI and cannot run inside the orm_skyway container at all. So they must
    # use the host-configured jx_home/driver-jar, not whatever this process
    # itself used internally (which may be the bundled in-container SDK path
    # when running inside Docker — see _DOCKER_JX_HOME).
    jx_home    = cfg.get("host_jx_home") or cfg["jx_home"]
    driver_jar = cfg.get("host_jdbc_driver_jar") or cfg["jdbc_driver_jar"]
    rel_config = config_path.relative_to(root)

    # Detect the correct javac release flags for the host JDK.
    # --release was introduced in Java 9; Java 8 needs -source/-target instead.
    try:
        _jv = subprocess.run(["javac", "-version"], capture_output=True, text=True)
        _jv_str = (_jv.stdout or _jv.stderr).strip()
        _major = int(_jv_str.split()[-1].split(".")[0])
        _java9p = _major >= 9 or (_major == 1 and int(_jv_str.split()[-1].split(".")[1]) >= 9)
    except Exception:
        _java9p = False
    javac_flags = "javac --release 8" if _java9p else "javac -source 8 -target 8"

    # setEnvironment.sh
    write_sh(root / "setEnvironment.sh", textwrap.dedent(f"""\
        #!/bin/bash
        export JX_HOME="{jx_home}"
        export CLASSPATH=.:{BIN_DIR}:{CONFIG_DIR}{f':{cfg["jdx_dev_bin_path"]}' if cfg.get("jdx_dev_bin_path") else ""}:"$JX_HOME/libs/jxclasses.jar":"$JX_HOME/libs/jdxtools.jar":"$JX_HOME/external_libs/json-20240303.jar":"{driver_jar}"
    """))

    # setEnvironment.bat
    (root / "setEnvironment.bat").write_text(textwrap.dedent(f"""\
        @echo off
        set JX_HOME={jx_home}
        set CLASSPATH=.;{BIN_DIR};{CONFIG_DIR}{f";{cfg['jdx_dev_bin_path']}" if cfg.get("jdx_dev_bin_path") else ""};%JX_HOME%\\libs\\jxclasses.jar;%JX_HOME%\\libs\\jdxtools.jar;%JX_HOME%\\external_libs\\json-20240303.jar;{driver_jar}
    """), encoding="utf-8")

    # JDXReverseEngineer.sh
    write_sh(root / "JDXReverseEngineer.sh", textwrap.dedent(f"""\
        #!/bin/bash
        source ./setEnvironment.sh
        java -DJX_HOME="$JX_HOME" com.softwaretree.jdxtools.JDXSchema -reverseEng {rel_config}
    """))

    # JDXReverseEngineer.bat
    (root / "JDXReverseEngineer.bat").write_text(textwrap.dedent(f"""\
        @echo off
        call setEnvironment
        java -DJX_HOME=%JX_HOME% com.softwaretree.jdxtools.JDXSchema -reverseEng {rel_config}
    """), encoding="utf-8")

    # Derive the package subdirectory path for clean step in scripts
    _pkg = cfg["object_model_package"]
    pkg_path_fwd  = "/".join(_pkg.split(".")) if _pkg else ""
    pkg_path_back = "\\".join(_pkg.split(".")) if _pkg else ""

    # compile.sh
    write_sh(root / "compile.sh", textwrap.dedent(f"""\
        #!/bin/bash
        source ./setEnvironment.sh
        # Clean the package bin directory to remove stale .class files
        rm -rf {BIN_DIR}/{pkg_path_fwd}
        mkdir -p {BIN_DIR}/{pkg_path_fwd}
        find {SRC_DIR} -name "*.java" > sources.txt
        {javac_flags} -d {BIN_DIR} -cp .:{BIN_DIR}:"$JX_HOME/libs/jxclasses.jar":"$JX_HOME/external_libs/json-20240303.jar":"{driver_jar}" @sources.txt
        if [ $? -eq 0 ]; then
            echo "Compilation completed successfully."
        else
            echo "Compilation failed."
            exit 1
        fi
    """))

    # compile.bat
    (root / "compile.bat").write_text(textwrap.dedent(f"""\
        @echo off
        call setEnvironment
        rem Clean the package bin directory to remove stale .class files
        if exist {BIN_DIR}\\{pkg_path_back} rmdir /s /q {BIN_DIR}\\{pkg_path_back}
        mkdir {BIN_DIR}\\{pkg_path_back}
        dir /s /b {SRC_DIR}\\*.java > sources.txt
        {javac_flags} -d {BIN_DIR} -cp .;{BIN_DIR};%JX_HOME%\\libs\\jxclasses.jar;%JX_HOME%\\external_libs\\json-20240303.jar;{driver_jar} @sources.txt
        if %ERRORLEVEL% == 0 (
            echo Compilation completed successfully.
        ) else (
            echo Compilation failed.
            exit /b 1
        )
    """), encoding="utf-8")

    # JDXDemo.bat
    (root / "JDXDemo.bat").write_text(textwrap.dedent("""        @echo off
        call setEnvironment
        java -DJX_HOME=%JX_HOME% com.softwaretree.jdxtools.JDXDemo config\\JDXDemo.config
    """), encoding="utf-8")

    # JDXDemo.sh
    write_sh(root / "JDXDemo.sh", textwrap.dedent("""        #!/bin/bash
        source ./setEnvironment.sh
        java -DJX_HOME="$JX_HOME" com.softwaretree.jdxtools.JDXDemo config/JDXDemo.config
    """))

    # JDXDemo.config — points at .jdx (working ORM spec) and lists fully-qualified class names
    jdx_orm_path = f"config/{cfg['reverse_eng_template_config']}.config.jdx"
    package      = cfg["object_model_package"]
    # selected_tables here is a list of class names (already renamed by user)
    class_list   = " ".join(f"{package}.{cls}" if package else cls for cls in selected_tables)
    (root / CONFIG_DIR / "JDXDemo.config").write_text(
        f"JDX_ORMFile {jdx_orm_path}\n"
        f"Classes {class_list}\n",
        encoding="utf-8"
    )

    info("Helper scripts written (setEnvironment, JDXReverseEngineer, compile, JDXDemo).")


# ==============================================================================
# 7.  RUN JDXSCHEMA REVERSE ENGINEER
# ==============================================================================

def run_reverse_engineer(cfg: dict, config_path: Path):

    root       = cfg["project_root"]
    jx_home    = cfg["jx_home"]
    driver_jar = cfg["jdbc_driver_jar"]
    pkg_rel    = pkg_to_rel(cfg["object_model_package"])
    src_pkg    = root / SRC_DIR if pkg_rel == Path(".") else root / SRC_DIR / pkg_rel

    # Wipe the entire src/ and bin/ directories before reverse-engineering.
    # Wiping src/ entirely (not just src/<current_pkg>/) ensures that .java
    # files from a previous run using a different object_model_package are not
    # picked up by the compile step and compiled into bin/.
    # Wiping bin/ entirely ensures no stale .class files from any previous run
    # — different tables, class names, or package — end up in the Docker image.
    src_dir = root / SRC_DIR
    if src_dir.exists():
        if _YES:
            info(f"{SRC_DIR}/ already exists from a previous run — recreating.")
        else:
            warn(f"{SRC_DIR}/ already exists from a previous run.")
            warn("If you have hand-edited any .java files under src/, save copies before continuing.")
        if not yn_confirm(f"OK to delete and recreate {SRC_DIR}/?", default=True):
            info("Aborted. Save any hand-edited .java files, then re-run.")
            sys.exit(0)
        shutil.rmtree(str(src_dir))
        verbose_info(f"Cleaned entire {SRC_DIR}/ directory")
    src_pkg.mkdir(parents=True, exist_ok=True)

    bin_dir = root / BIN_DIR
    if bin_dir.exists():
        shutil.rmtree(str(bin_dir))
        verbose_info(f"Cleaned entire {BIN_DIR}/ directory")
    bin_dir.mkdir(parents=True, exist_ok=True)

    (root / BIN_DIR).mkdir(parents=True, exist_ok=True)

    cp = _build_cp(cfg,
        str(root / BIN_DIR),
        str(root / CONFIG_DIR),
        str(Path(jx_home) / "libs" / "jxclasses.jar"),
        str(Path(jx_home) / "libs" / "jdxtools.jar"),
        str(Path(jx_home) / "external_libs" / "json-20240303.jar"),
        driver_jar,
        ".",
    )

    cmd = [
        "java",
        f"-DJX_HOME={jx_home}",
        "-cp", cp,
        "com.softwaretree.jdxtools.JDXSchema",
        "-reverseEng",
        str(config_path.resolve()),
    ]
    verbose_info(f"Command: {' '.join(cmd)}")

    # Run from project root — JDXSchema drops .java files in cwd.
    # Pipe 'A' (AlwaysYes) to stdin so JDXSchema automatically answers 'Yes'
    # to any 'overwrite existing file?' prompts without requiring user input.
    # Capture output — show only in verbose mode to avoid noisy banner/warnings
    # cluttering normal runs.
    ret = subprocess.run(cmd, cwd=str(root), input="A\n", text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if _VERBOSE and ret.stdout:
        print(ret.stdout.rstrip())
    # JDXSchema may exit with code 0 even on fatal errors (e.g. unknown JDX_DBTYPE).
    # Detect failure by checking for "Exception:" in output as well as returncode.
    _jdx_failed = (ret.returncode != 0 or
                   (ret.stdout and ": Exception:" in ret.stdout))
    if _jdx_failed:
        _surface_jdx_error(
            ret.stdout or "",
            "JDXReverseEngineer (JDXSchema -reverseEng) exited with an error."
        )
        sys.exit(1)
    info("Reverse engineering completed.")



# ==============================================================================
# 9.  COPY JDBC JAR INTO config/ (for Gilhari Docker packaging)
# ==============================================================================

def copy_jdbc_jar_to_config(cfg: dict):
    """
    Copy the JDBC driver JAR into config/ so it is co-located with the ORM
    spec files and can be bundled into a Gilhari Docker image cleanly.
    Skipped silently if the JAR is already inside config/.

    Also copies an accompanying license file if one exists — some JDBC
    drivers (e.g. CData's) ship as jar + .lic side by side and fail at
    runtime with a "valid license not found" error if only the jar is
    bundled into the image. Auto-detected as a same-stem sibling file
    (cdata.jdbc.excel.jar -> cdata.jdbc.excel.lic); an explicit path via
    cfg["jdbc_driver_lic"] / --jdbc-driver-lic overrides the auto-detection
    for drivers that don't follow that naming convention.
    """
    root       = cfg["project_root"]
    driver_jar = Path(cfg["jdbc_driver_jar"]).resolve()
    config_dir = (root / CONFIG_DIR).resolve()
    dest       = config_dir / driver_jar.name

    already_in_config = driver_jar.parent.resolve() == config_dir
    if already_in_config:
        info(f"JDBC driver JAR already in config/: {driver_jar.name}")
    else:
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(driver_jar), str(dest))
        info(f"JDBC driver JAR copied to config/{driver_jar.name}  (for Docker packaging)")

    # License file: explicit override wins; otherwise look for a same-stem
    # .lic file next to the jar.
    _explicit_lic = (cfg.get("jdbc_driver_lic") or "").strip()
    lic_src = Path(_explicit_lic).resolve() if _explicit_lic else driver_jar.with_suffix(".lic")

    if lic_src.is_file():
        lic_dest = config_dir / lic_src.name
        if lic_src.resolve() == lic_dest.resolve():
            info(f"JDBC driver license already in config/: {lic_src.name}")
        else:
            config_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(lic_src), str(lic_dest))
            info(f"JDBC driver license copied to config/{lic_src.name}  (for Docker packaging)")
    elif _explicit_lic:
        warn(f"jdbc_driver_lic was set to {_explicit_lic!r} but that file was not found — "
             f"the Docker image will be built without it.")


# ==============================================================================
# 9b. COPY .revjdx -> .jdx  (user-editable ORM specification)
# ==============================================================================

def copy_revjdx_to_jdx(config_path: Path) -> Path:
    """
    Copy the generated .revjdx file to a .jdx file of the same base name.
    .revjdx  = immutable record of the reverse-engineered starting point.
    .jdx     = working copy the user refines over time for downstream use.
    Returns the Path of the .jdx file.
    """
    revjdx = config_path.with_suffix(".config.revjdx")
    jdx    = config_path.with_suffix(".config.jdx")

    if not revjdx.exists():
        warn(f".revjdx file not found: {revjdx.name}  (reverse-engineering may have failed)")
        return jdx

    if jdx.exists():
        if _YES:
            info(f"Working ORM file already exists: {jdx.name} — auto-selecting [R] Replace.")
            choice = "R"
        else:
            print("  [R] Replace  - overwrite with the freshly generated .revjdx (recommended)")
            print("  [K] Keep     - leave the existing .jdx untouched (only if you have Phase 2 edits to preserve)")
            while True:
                choice = ask("Your choice [R/K]", "R").strip().upper()
                if choice in ("K", "R"):
                    break
        if choice == "K":
            info(f"Keeping existing {jdx.name}")
            return jdx

    shutil.copy2(str(revjdx), str(jdx))
    info(f"Working ORM spec created: {jdx.name}  (edit this file for further refinements)")
    verbose_info(f"  Original preserved as:  {revjdx.name}  (do not edit)")
    verbose_info(f"  Both use localhost — safe for JDXDemo and local Java use.")
    verbose_info(f"  A Docker-specific copy (.docker.jdx) will be created in Phase 3.")
    return jdx


# ==============================================================================
# 10. COMPILE GENERATED CLASSES
# ==============================================================================


def compile_classes(cfg: dict):

    root       = cfg["project_root"].resolve()
    jx_home    = cfg["jx_home"]
    driver_jar = cfg["jdbc_driver_jar"]
    src_dir    = root / SRC_DIR
    bin_dir    = root / BIN_DIR

    java_files = list(src_dir.rglob("*.java"))
    if not java_files:
        warn(f"No .java files found under {SRC_DIR}/. Nothing to compile.")
        return

    # Ensure bin/<pkg>/ exists (bin/ was wiped in run_reverse_engineer;
    # bin/<pkg>/ just needs to exist for javac to write into).
    package = cfg["object_model_package"]
    pkg_rel = pkg_to_rel(package)
    bin_pkg = bin_dir if pkg_rel == Path(".") else bin_dir / pkg_rel
    bin_pkg.mkdir(parents=True, exist_ok=True)

    # Write sources.txt with absolute paths so @sources.txt works anywhere
    sources_txt = root / "sources.txt"
    sources_txt.write_text(
        "\n".join(str(f.resolve()) for f in java_files),
        encoding="utf-8"
    )
    verbose_info(f"Found {len(java_files)} Java source file(s).")

    bin_dir.mkdir(parents=True, exist_ok=True)

    cp = _build_cp(cfg,
        str(bin_dir),
        str(Path(jx_home) / "libs" / "jxclasses.jar"),
        str(Path(jx_home) / "external_libs" / "json-20240303.jar"),
        driver_jar,
    )

    # Detect javac version — --release was introduced in Java 9.
    # On Java 8, fall back to -source 8 -target 8 (also a no-op on Java 8
    # but accepted without error, unlike --release).
    try:
        _ver = subprocess.run(["javac", "-version"], capture_output=True, text=True)
        _ver_str = (_ver.stdout or _ver.stderr).strip()  # 'javac X.Y.Z'
        _major = int(_ver_str.split()[-1].split(".")[0])
        _java9_plus = _major >= 9 or (_major == 1 and int(_ver_str.split()[-1].split(".")[1]) >= 9)
    except Exception:
        _java9_plus = False
    _release_flags = ["--release", "8"] if _java9_plus else ["-source", "8", "-target", "8"]

    cmd = [
        "javac",
        *_release_flags,
        "-d", str(bin_dir),
        "-cp", cp,
        f"@{sources_txt.resolve()}",
    ]
    verbose_info(f"Command: {' '.join(cmd)}")

    ret = subprocess.run(cmd, capture_output=False, text=True)
    if ret.returncode != 0:
        error("Compilation failed (see output above).")
        sys.exit(1)
    info("Compilation completed successfully.")



# ==============================================================================
# 11b. WRITE GILHARI MICROSERVICE ARTIFACTS
# ==============================================================================


def _is_file_based_jdbc(jdbc_url: str) -> bool:
    """Return True if the JDBC URL refers to a file-based (embedded) database.
    These require special Docker handling: volume mount or embed.
    Covers SQLite, H2 file mode, HSQLDB file mode, Derby embedded, Excel.
    """
    u = jdbc_url.lower()
    return (
        "jdbc:sqlite:"      in u or
        "jdbc:h2:file:"     in u or
        "jdbc:hsqldb:file:" in u or
        "jdbc:excel:"       in u or
        ("jdbc:derby:" in u and "://" not in u)  # embedded only, not server mode
    )


def _resolve_db_file_info(cfg: dict) -> dict:
    """For file-based databases, resolve the DB file path and compute Docker paths.

    Returns a dict with:
      host_db_dir      - absolute Path of the directory containing the DB file on host
      db_filename      - bare filename (e.g. mydb.sqlite)
      container_db_dir - fixed container path: /opt/<image_name>/db
      container_db_url - rewritten JDBC URL for .docker.jdx
      mount_arg        - docker run -v argument (host_dir:container_dir)
    """
    import re as _re2
    root       = cfg["project_root"].resolve()
    image_name = cfg.get("docker_image_name", "gilhari-service")
    jdbc_url   = cfg["jdbc_url"]

    # Extract the file path from the JDBC URL
    # Patterns: jdbc:sqlite:./path/db.sqlite  or  jdbc:sqlite:/abs/path/db.sqlite
    #           jdbc:h2:file:./path/mydb      or  jdbc:excel:URI=./path/file.xlsx
    # Normalise Windows backslashes to forward slashes first
    url_norm = jdbc_url.replace("\\", "/")

    # Try to extract path after the JDBC sub-protocol
    # sqlite:  jdbc:sqlite:<path>
    # h2:      jdbc:h2:file:<path>
    # hsqldb:  jdbc:hsqldb:file:<path>
    # derby:   jdbc:derby:<path>
    # excel:   jdbc:excel:URI=<path>  (may have extra params after ;)
    _pats = [
        r'jdbc:sqlite:(.+)',
        r'jdbc:h2:file:(.+)',
        r'jdbc:hsqldb:file:(.+)',
        r'jdbc:derby:([^;]+)',
        r'jdbc:excel:[^=]*URI=([^;]+)',
    ]
    raw_path = None
    for pat in _pats:
        m = _re2.search(pat, url_norm, _re2.IGNORECASE)
        if m:
            raw_path = m.group(1).strip()
            break

    if not raw_path:
        warn("Could not extract DB file path from JDBC URL — file-based Docker handling skipped.")
        return {}

    # Resolve to absolute path
    p = Path(raw_path)
    if not p.is_absolute():
        p = (root / p).resolve()
    else:
        # Normalise Windows drive letters: C:/path -> /c/path for Docker
        p = Path(raw_path.replace("\\", "/"))
        if len(raw_path) > 1 and raw_path[1] == ":":
            # Windows absolute: C:/path/db.sqlite
            drive = raw_path[0].lower()
            rest  = raw_path[2:].replace("\\", "/")
            p = Path(f"/{drive}{rest}")

    host_db_dir    = p.parent
    db_filename    = p.name

    # FA1: when orm_skyway.py runs inside the softwaretree/orm_skyway
    # container, `root` above is /project (the in-container bind-mount
    # point) — not a real path on the developer's machine. Translate
    # host_db_dir back to the actual host-side path; without this,
    # generated scripts like run_docker_app.cmd/.sh — which run later,
    # directly on the host, not inside this container — would bake in a
    # meaningless "/project/..." bind-mount source.
    if _running_in_docker():
        _translated = _container_path_to_host(host_db_dir, root, what="DB file directory")
        if _translated:
            host_db_dir = Path(_translated)

    container_db_dir = f"/opt/{image_name}/db"
    container_db_url = _re2.sub(
        r'(jdbc:sqlite:|jdbc:h2:file:|jdbc:hsqldb:file:|jdbc:derby:).*',
        lambda m: m.group(1) + f"{container_db_dir}/{db_filename}",
        url_norm, flags=_re2.IGNORECASE
    )
    # For Excel: rewrite URI= portion
    if "jdbc:excel:" in url_norm.lower():
        container_db_url = _re2.sub(
            r'URI=[^;]+', f"URI={container_db_dir}/{db_filename}",
            url_norm, flags=_re2.IGNORECASE
        )

    # Docker volume mount arg — always use forward slashes
    host_dir_str = str(host_db_dir).replace("\\", "/")
    mount_arg = f"{host_dir_str}:{container_db_dir}"

    return {
        "host_db_dir":      host_db_dir,
        "db_filename":      db_filename,
        "container_db_dir": container_db_dir,
        "container_db_url": container_db_url,
        "mount_arg":        mount_arg,
    }


def create_docker_jdx(cfg: dict, config_path: Path) -> Path:
    """
    Create a Docker-specific ORM spec by copying the working .jdx file and
    replacing localhost/127.0.0.1 with host.docker.internal in the
    JDX_DATABASE line.  This copy is what gets packaged into the Docker image.

    File roles:
      .jdx          <- working copy, localhost, used by JDXDemo and local Java apps
      .docker.jdx   <- Docker copy, host.docker.internal, packaged in the image
    """
    jdx        = config_path.with_suffix(".config.jdx")
    docker_jdx = config_path.with_suffix(".config.docker.jdx")

    if not jdx.exists():
        error(f"Working ORM spec not found: {jdx.name}")
        error("Has Phase 1 been run and the .revjdx copied to .jdx?")
        sys.exit(1)

    text = jdx.read_text(encoding="utf-8")
    docker_text = text

    if _is_file_based_jdbc(cfg["jdbc_url"]):
        # File-based DB: rewrite JDBC URL to fixed container path.
        # The working .jdx keeps the original path for local use.
        db_info = _resolve_db_file_info(cfg)
        if db_info:
            cfg["_db_file_info"] = db_info  # pass to write_gilhari_artifacts
            import re as _re3
            # Replace the JDX_DATABASE line URL with the container URL
            docker_text = _re3.sub(
                r'(JDX_DATABASE\s+JDX:)([^;\n]+)(.*)',
                lambda m: m.group(1) + db_info["container_db_url"] + m.group(3),
                docker_text
            )
            info(f"Docker ORM spec created: {docker_jdx.name}")
            verbose_info(f"  File-based DB URL rewritten to: {db_info['container_db_url']}")
    else:
        # Network-based DB: replace localhost with host.docker.internal
        docker_text = _docker_safe_jdbc_url(docker_text)
        if docker_text != text:
            info(f"Docker ORM spec created: {docker_jdx.name}")
            verbose_info(f"  localhost -> host.docker.internal  (for DB access from inside container)")
        else:
            info(f"Docker ORM spec created: {docker_jdx.name}  (no URL change needed)")

    docker_jdx.write_text(docker_text, encoding="utf-8")
    return docker_jdx

def _find_stale_or_uncompiled_java_files(cfg: dict) -> list:
    """Return .java files under src/ that are newer than their corresponding
    .class file in bin/, or have no .class file there at all (e.g. a brand
    new class added during a Phase 2 hand-edit). Phase 3 packages whatever
    is currently sitting in bin/ as-is — it never recompiles — so this lets
    Phase 3 warn rather than silently ship stale or missing compiled code.

    Best-effort: only checks top-level (non-inner) class name matches by
    relative path under src/<pkg> vs bin/<pkg>. A class that was renamed or
    deleted in src/ without removing the old .class from bin/ is not
    detected here (that's still fine to ship; it just won't be referenced).
    """
    root    = cfg["project_root"].resolve()
    src_dir = root / SRC_DIR
    bin_dir = root / BIN_DIR
    if not src_dir.exists():
        return []

    stale = []
    for java_file in src_dir.rglob("*.java"):
        rel = java_file.relative_to(src_dir)
        class_file = bin_dir / rel.with_suffix(".class")
        if not class_file.exists():
            stale.append(java_file)
        elif java_file.stat().st_mtime > class_file.stat().st_mtime:
            stale.append(java_file)
    return stale


_JDX_SANDBOX_DIRNAME = "jdx_sandbox"

# Confirmed via: docker run --rm softwaretree/gilhari find / -iname "LICENSE*"
_DOCKER_GILHARI_LICENSE_PATH = "/node/node_modules/gilhari_rest_server/LICENSE.txt"

# Files needed on the host for JDXDemo.bat/.sh to run there later (it cannot
# run inside the orm_skyway container — Swing GUI needs a real display).
# Relative to _DOCKER_JX_HOME inside the image; same relative layout is
# recreated under <project>/jdx_sandbox/ on the host.
_JDX_SANDBOX_FILES = [
    "libs/jxclasses.jar",
    "libs/jdxtools.jar",
    "external_libs/json-20240303.jar",
    "config/jdx.lic",
]


def _create_jdx_sandbox(cfg: dict):
    """Copy the JDX SDK jars + license bundled in the softwaretree/orm_skyway
    image into <project>/jdx_sandbox/, and return the host-side path to use
    as JX_HOME — or None on failure.

    For users with no local JDX install at all. They still need *some* local
    JDK (java/javac) on the host to run JDXDemo.bat/.sh — this sandbox only
    supplies the JDX classes and license, which are pure platform-independent
    Java bytecode/text. The JDK binaries inside the image are Linux ELF
    binaries and cannot be extracted for use on Windows/macOS hosts.
    """
    root = cfg["project_root"].resolve()
    sandbox_container_dir = root / _JDX_SANDBOX_DIRNAME

    missing = []
    for rel in _JDX_SANDBOX_FILES:
        src = Path(_DOCKER_JX_HOME) / rel
        if not src.is_file():
            missing.append(rel)
    if missing:
        warn(
            "Could not create a JDX sandbox — these files were not found in the "
            f"image's bundled SDK at {_DOCKER_JX_HOME}: {', '.join(missing)}. "
            "JDXDemo.bat/.sh will not be runnable without a local JDX install."
        )
        return None

    for rel in _JDX_SANDBOX_FILES:
        src = Path(_DOCKER_JX_HOME) / rel
        dst = sandbox_container_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    info(f"JDX sandbox created at {_JDX_SANDBOX_DIRNAME}/ (jxclasses.jar, jdxtools.jar, json-20240303.jar, jdx.lic).")

    # Also copy the Gilhari product license into the sandbox root. Purely
    # informational (the JDX jars/jdx.lic above are what's actually required
    # for JDXDemo to run) — non-fatal if not found, since image layouts can
    # change between Gilhari releases.
    _license_src = Path(_DOCKER_GILHARI_LICENSE_PATH)
    if _license_src.is_file():
        shutil.copy2(_license_src, sandbox_container_dir / _license_src.name)
        info(f"Gilhari LICENSE copied to {_JDX_SANDBOX_DIRNAME}/{_license_src.name}")
    else:
        verbose_info(f"Gilhari LICENSE not found at {_DOCKER_GILHARI_LICENSE_PATH} — skipped (non-fatal).")

    host_path = _container_path_to_host(sandbox_container_dir, root, what="JDX sandbox directory")
    if not host_path:
        warn(
            f"Could not translate the JDX sandbox directory to a host path. "
            f"Set jx_home in orm_skyway_config.json manually to the {_JDX_SANDBOX_DIRNAME}/ "
            f"directory under your project (its real path on this host)."
        )
        return None

    info(f"setEnvironment.bat/.sh will use JX_HOME={host_path}")
    info(
        "Note: you still need a JDK (java/javac) installed on this host to run "
        "JDXDemo.bat/.sh — the sandbox supplies only the JDX classes and license, "
        "not a JDK (the image's JDK is a Linux binary and can't be used on this host)."
    )
    return host_path


def revert_docker_url_in_host_artifacts(cfg: dict, config_path: Path):
    """In Docker mode, config/*.config, *.revjdx, and *.jdx are generated
    using the Docker-rewritten JDBC URL (host.docker.internal) because that's
    what's needed for the live connection during reverse engineering. But
    these specific files are also meant to remain directly usable on the
    host afterward — most importantly for JDXDemo.bat/.sh, which cannot run
    inside the orm_skyway container at all (see host_jx_home). So once
    generation is done, rewrite the embedded URL in these files back to the
    original host-facing value. (.docker.jdx, generated later in Phase 3, is
    unaffected here — it's *supposed* to carry the Docker-internal URL.)

    No-op outside Docker, or when jdbc_url was never rewritten in the first
    place (remote DB, container-name DB, file-based DB — see _docker_safe_jdbc_url).
    """
    if not _running_in_docker():
        return
    live_url = cfg.get("effective_jdbc_url") or cfg.get("jdbc_url")
    host_url = cfg.get("host_effective_jdbc_url") or cfg.get("host_jdbc_url")
    if not live_url or not host_url or live_url == host_url:
        return  # nothing to revert

    targets = [
        config_path,
        config_path.with_suffix(".config.revjdx"),
        config_path.with_suffix(".config.jdx"),
    ]
    reverted = []
    for f in targets:
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        if live_url in text:
            f.write_text(text.replace(live_url, host_url), encoding="utf-8")
            reverted.append(f.name)
    if reverted:
        verbose_info(
            f"Restored host-facing JDBC URL ({host_url}) in: {', '.join(reverted)} "
            f"— these files must work directly on the host for JDXDemo."
        )


def discover_classes_from_bin(cfg: dict) -> list:
    """
    Scan bin/<package path>/ for compiled .class files and return a list of
    simple (unqualified) top-level class names — i.e. no $ inner classes.
    These reflect whatever the user actually compiled after any Phase 2 edits.
    All .class files (including inner classes) are still bundled in the Docker
    image via ADD bin ./bin in the Dockerfile.
    """
    root    = cfg["project_root"].resolve()
    package = cfg["object_model_package"]
    pkg_rel = pkg_to_rel(package)
    bin_pkg = root / BIN_DIR if pkg_rel == Path(".") else root / BIN_DIR / pkg_rel

    if not bin_pkg.exists():
        warn(f"bin/{pkg_rel} not found. Has Phase 1 (compile) been run?")
        return []

    top_level = sorted(
        f.stem for f in bin_pkg.glob("*.class")
        if "$" not in f.stem          # exclude inner / anonymous classes
        and not f.stem.startswith("_")
    )
    if not top_level:
        warn(f"No .class files found in {bin_pkg.relative_to(root)}")
    return top_level


def write_gilhari_artifacts(cfg: dict, config_path: Path, class_names: list):
    """
    Generate all files needed to build and run a Gilhari RESTful microservice.
    class_names: list of simple (unqualified) top-level class names,
                 discovered from bin/ so they reflect post-Phase-2 state.

    Files written:
      config/classnames_map.json   - maps short REST name -> FQN
      gilhari_service.config     - runtime service configuration (JSON)
      Dockerfile                 - builds image from softwaretree/gilhari base
      build.cmd / build.sh       - docker build scripts
      run_docker_app.cmd / .sh   - docker run scripts
    """
    import json as _json

    header("Phase 3 - Step 3 - Generate Docker ORM Spec")

    root         = cfg["project_root"]
    config_name  = cfg["reverse_eng_template_config"]
    package      = cfg["object_model_package"]
    image_name   = cfg.get("docker_image_name") or config_name.lower().replace("_", "-")
    image_tag    = cfg.get("docker_image_tag", "1.0")
    host_port    = cfg.get("gilhari_host_port", 80)
    service_port = 8081
    driver_jar   = Path(cfg["jdbc_driver_jar"])
    container_jar_path = f"/opt/{image_name}/config/{driver_jar.name}"
    classnames_map_file = f"config/classnames_map.json"

    # Create the Docker-specific ORM spec (.docker.jdx) from the working
    # .jdx — replacing localhost with host.docker.internal.  The working
    # .jdx is left untouched for JDXDemo and local Java use.
    docker_jdx = create_docker_jdx(cfg, config_path)
    docker_jdx_rel = f"./config/{docker_jdx.name}"

    if not class_names:
        error("No compiled classes found. Cannot generate Gilhari artifacts.")
        return

    header("Phase 3 - Step 4 - Generate Gilhari Service Artifacts")
    info(f"Classes found in bin/: {', '.join(class_names)}")
    # ── config/classnames_map.json ──────────────────────────────────────────────
    # Maps simple class name (REST URL token) -> fully-qualified class name.
    # Short name == simple class name — keeps REST URL, ORM spec, and SQL
    # all using the same name, avoiding confusion during debugging.
    classnames_map = {cls: f"{package}.{cls}" if package else cls for cls in class_names}
    map_path = root / CONFIG_DIR / "classnames_map.json"
    map_path.write_text(
        _json.dumps(classnames_map, indent=2) + "\n",
        encoding="utf-8"
    )
    info(f"Written: {classnames_map_file}")
    for short, fqn in classnames_map.items():
        verbose_info(f"  {short}  ->  {fqn}")

    # ── gilhari_service.config ────────────────────────────────────────────────
    service_cfg = {
        "gilhari_microservice_name":       image_name,
        "jdx_orm_spec_file":               docker_jdx_rel,
        "jdbc_driver_path":                container_jar_path,
        "jdx_debug_level":                 5,
        "jdx_force_create_schema":         "false",
        "jdx_persistent_classes_location": "./bin",
        "classnames_map_file":             classnames_map_file,
        "gilhari_rest_server_port":        service_port,
    }
    svc_path = root / "gilhari_service.config"
    svc_path.write_text(_json.dumps(service_cfg, indent=2) + "\n", encoding="utf-8")
    verbose_info("Written: gilhari_service.config")

    # ── Dockerfile ────────────────────────────────────────────────────────────
    _db_info   = cfg.get("_db_file_info", {})
    _file_db   = bool(_db_info)
    _embed     = cfg.get("embed_db_file_in_microservice", False) and _file_db

    _dockerfile_lines = [
        f"# Gilhari RESTful microservice: {image_name}",
        f"# Generated by orm_skyway.py",
        f"# Builds on the base Gilhari image (REST server pre-installed).",
        f"ARG BASE_PLATFORM={cfg['docker_platform']}",
        f"FROM --platform=${{BASE_PLATFORM}} softwaretree/gilhari",
        f"",
        f"WORKDIR /opt/{image_name}",
        f"",
        f"# bin/ includes all .class files (top-level and inner classes)",
        f"# config/ includes .docker.jdx ORM spec, JDBC driver JAR, classnames_map.json",
        f"ADD bin ./bin",
        f"ADD config ./config",
        f"ADD gilhari_service.config .",
    ]
    if _embed:
        # Embed mode: copy the DB directory into the image
        _host_dir  = _db_info["host_db_dir"]
        _cont_dir  = _db_info["container_db_dir"]
        # Compute relative path of host_db_dir from project root for ADD
        try:
            _rel_host = _host_dir.relative_to(root)
            _add_src  = str(_rel_host).replace("\\", "/")
        except ValueError:
            # host_db_dir is outside project root — copy to a temp location
            _add_src  = f"db_embed"
            import shutil as _shutil
            _embed_tmp = root / "db_embed"
            _embed_tmp.mkdir(exist_ok=True)
            import glob as _glob
            for _f in _host_dir.glob("*"):
                _shutil.copy2(str(_f), str(_embed_tmp / _f.name))
            warn(f"DB directory is outside project root — copied to db_embed/ for Docker packaging.")
        _dockerfile_lines += [
            f"",
            f"# SQLite/file-based database embedded in image (embed_db_file_in_microservice: true)",
            f"# NOTE: data is baked in at build time -- rebuild the image to pick up DB changes.",
            f"ADD {_add_src} {_cont_dir}",
        ]
    elif _file_db:
        _dockerfile_lines += [
            f"",
            f"# File-based database: NOT embedded -- mounted at runtime via -v flag.",
            f"# See run_docker_app.cmd / run_docker_app.sh for the mount command.",
        ]
    _dockerfile_lines += [
        f"",
        f"EXPOSE {service_port}",
        f"",
        f'CMD ["node", "/node/node_modules/gilhari_rest_server/gilhari_rest_server.js", "gilhari_service.config"]',
    ]
    dockerfile = "\n".join(_dockerfile_lines) + "\n"
    (root / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    verbose_info(f"Written: Dockerfile  ({image_name}:{image_tag}, port {host_port}->{service_port})")

    # ── build.cmd / build.sh ──────────────────────────────────────────────────
    # The legacy-builder warning only fires when buildx isn't available, which
    # is true inside the orm_skyway image (bare docker.io CLI, no buildx
    # plugin) but not on a typical host with Docker Desktop. These scripts may
    # run in either context later, so check at runtime rather than assuming.
    (root / "build.cmd").write_text(
        f"docker buildx version >nul 2>&1\r\n"
        f"if errorlevel 1 echo Note: a 'legacy builder is deprecated' warning below (if shown) is harmless.\r\n"
        f"docker build --platform {cfg['docker_platform']} -t {image_name}:{image_tag} .\r\n"
        f"docker images\r\n",
        encoding="utf-8"
    )
    write_sh(root / "build.sh",
        f"#!/bin/bash\n"
        f"docker buildx version >/dev/null 2>&1 || "
        f"echo \"Note: a 'legacy builder is deprecated' warning below (if shown) is harmless.\"\n"
        f"docker build --platform {cfg['docker_platform']} -t {image_name}:{image_tag} .\n"
        f"docker images\n"
    )
    verbose_info("Written: build.cmd / build.sh")

    # ── .dockerignore for file-based DBs ───────────────────────────────────
    # In embed mode: remove any existing .dockerignore that might exclude the
    # DB file — a leftover from a previous mount-mode run would prevent the
    # ADD instruction from copying the DB file into the image.
    _dockerignore_path = root / ".dockerignore"
    if _file_db and _embed:
        if _dockerignore_path.exists():
            _dockerignore_path.unlink()
            info(".dockerignore removed — embed mode requires DB file to be copied into image.")
    elif _file_db and not _embed:
        _host_dir  = _db_info["host_db_dir"]
        try:
            _rel_dir = _host_dir.relative_to(root)
            # Exclude all files in the DB directory from the Docker build context
            _di_entry = str(_rel_dir).replace("\\", "/") + "/*"
        except ValueError:
            _di_entry = None  # outside project root — nothing to exclude
        if _di_entry:
            # Exclude only the DB file and its WAL/companion files by pattern,
            # NOT the entire directory — other files in config/ (classnames_map.json,
            # JDBC driver JAR, .docker.jdx etc.) must still be copied into the image.
            _db_stem   = _db_info["db_filename"]  # e.g. json2_example.db
            _db_dir_fwd = str(_rel_dir).replace("\\\\", "/").replace("\\", "/")
            # Handle db file directly in project root (e.g. ./db.sqlite)
            _prefix = _db_dir_fwd if _db_dir_fwd != "." else ""
            _sep    = "/" if _prefix else ""
            _di_lines = [
                "# Auto-generated by orm_skyway.py",
                "# File-based database excluded from Docker image (provided via volume mount).",
                "# Other files in the same directory are still copied into the image.",
                f"{_prefix}{_sep}{_db_stem}",
                f"{_prefix}{_sep}{_db_stem}-wal",
                f"{_prefix}{_sep}{_db_stem}-shm",
                f"{_prefix}{_sep}{_db_stem}.mv.db",
                f"{_prefix}{_sep}{_db_stem}.trace.db",
            ]
            _di_content = "\n".join(_di_lines) + "\n"
            _dockerignore_path.write_text(_di_content)
            verbose_info(f"Written: .dockerignore  (excludes {_db_stem} and companions)")

    # ── run_docker_app.cmd / run_docker_app.sh ────────────────────────────────
    _mount_flag_cmd = ""
    _mount_flag_sh  = ""
    if _file_db and not _embed:
        _ma = _db_info["mount_arg"]
        _mount_flag_cmd = f" -v \"{_ma}\""
        _mount_flag_sh  = f" -v \"{_ma}\""

    # --hostname defaults to the image name for stability across runs (Docker
    # otherwise assigns a new semi-random hostname per container), but is
    # overridable via cfg["docker_hostname"] — confirmed necessary for CData's
    # Excel driver (2026-07-13), which needs the hostname to match whatever
    # the license was actually issued/activated for, not an arbitrary value.
    # --mac-address is only added if explicitly configured (same reasoning).
    _hostname_value = cfg.get("docker_hostname") or image_name
    _identity_flags_cmd = f' --hostname {_hostname_value}'
    if cfg.get("docker_mac_address"):
        _identity_flags_cmd += f' --mac-address {cfg["docker_mac_address"]}'

    # ── run_docker_app.cmd / run_docker_app.sh ────────────────────────────────
    (root / "run_docker_app.cmd").write_text(
        f"@echo off\r\n"
        f"setlocal enabledelayedexpansion\r\n"
        f"REM Check if service is already running and healthy\r\n"
        f"curl.exe -fs --max-time 3 http://localhost:{host_port}/gilhari/v1/health/check >nul 2>&1\r\n"
        f"if not errorlevel 1 (\r\n"
        f"    echo Gilhari microservice is already running and healthy.\r\n"
        f"    echo REST base URL: http://localhost:{host_port}/gilhari/v1/\r\n"
        f"    exit /b 0\r\n"
        f")\r\n"
        f"REM Remove any existing container with this name (stopped or running)\r\n"
        f"docker rm -f {image_name} >nul 2>&1\r\n"
        f"docker run --platform {cfg['docker_platform']}{_identity_flags_cmd} -d --name {image_name}{_mount_flag_cmd} -p {host_port}:{service_port} {image_name}:{image_tag}\r\n"
        f"\r\n"
        f"echo Waiting for Gilhari microservice to start...\r\n"
        f"echo (This may take up to 3 minutes for cloud or remote databases)\r\n"
        f"set READY=0\r\n"
        f"for /L %%i in (1,1,18) do (\r\n"
        f"    curl.exe -fs http://localhost:{host_port}/gilhari/v1/health/check >nul 2>&1\r\n"
        f"    if not errorlevel 1 set READY=1\r\n"
        f"    if !READY!==1 goto :done\r\n"
        f"    timeout /t 10 /nobreak >nul\r\n"
        f")\r\n"
        f":done\r\n"
        f"if !READY!==1 (\r\n"
        f"    echo Gilhari microservice is up and ready.\r\n"
        f"    echo REST base URL: http://localhost:{host_port}/gilhari/v1/\r\n"
        f") else (\r\n"
        f"    echo Service did not respond after 180 seconds.\r\n"
        f"    echo The container may still be starting. Check: docker logs {image_name}\r\n"
        f"    echo To check if it started later: curl.exe -s http://localhost:{host_port}/gilhari/v1/health/check\r\n"
        f"    exit /b 1\r\n"
        f")\r\n",
        encoding="utf-8"
    )
    # --add-host flag: needed on macOS/Linux when host.docker.internal
    # does not resolve (e.g. Docker Desktop on macOS without network config,
    # or Linux). Not needed for file-based DBs which use volume mounts.
    _add_host_flag = "" if _file_db else " --add-host=host.docker.internal:host-gateway"

    _identity_flags_sh = f' --hostname {_hostname_value}'
    if cfg.get("docker_mac_address"):
        _identity_flags_sh += f' --mac-address {cfg["docker_mac_address"]}'

    write_sh(root / "run_docker_app.sh",
        f"#!/bin/bash\n"
        f"# Check if service is already running and healthy\n"
        f"if curl -fs --max-time 3 \"http://localhost:{host_port}/gilhari/v1/health/check\" > /dev/null 2>&1; then\n"
        f"    echo \"✔ Gilhari microservice is already running and healthy.\"\n"
        f"    echo \"  REST base URL: http://localhost:{host_port}/gilhari/v1/\"\n"
        f"    exit 0\n"
        f"fi\n"
        f"# Remove any existing container with this name (stopped or running)\n"
        f"docker rm -f {image_name} > /dev/null 2>&1 || true\n"
        f"docker run --platform {cfg['docker_platform']}{_identity_flags_sh}{_add_host_flag} -d --name {image_name}{_mount_flag_sh} -p {host_port}:{service_port} {image_name}:{image_tag}\n"
        f"\n"
        f"echo \"Waiting for Gilhari microservice to start...\"\n"
        f"echo \"(This may take up to 3 minutes for cloud or remote databases)\"\n"
        f"for i in $(seq 1 18); do\n"
        f"    if curl -fs \"http://localhost:{host_port}/gilhari/v1/health/check\" > /dev/null 2>&1; then\n"
        f"        echo \"✔ Gilhari microservice is up and ready.\"\n"
        f"        echo \"  REST base URL: http://localhost:{host_port}/gilhari/v1/\"\n"
        f"        exit 0\n"
        f"    fi\n"
        f"    sleep 10\n"
        f"done\n"
        f"echo \"✘ Service did not respond after 180 seconds.\"\n"
        f"echo \"  The container may still be starting. Check: docker logs {image_name}\"\n"
        f"echo \"  To check if it started later: curl -s http://localhost:{host_port}/gilhari/v1/health/check\"\n"
        f"exit 1\n",
    )
    verbose_info(f"Written: run_docker_app.cmd / run_docker_app.sh  (host port: {host_port})")

    header("Phase 3 - Step 5 - Generate Sample Curl Scripts")
    write_curl_scripts(cfg, class_names)
    write_curl_write_scripts(cfg, class_names)
    header("Phase 3 - Step 6 - Generate ORMCP Connection Guide")
    write_ormcp_guide(cfg, class_names)

    # ── Info messages for file-based DB handling ─────────────────────────────
    if _file_db:
        if _embed:
            warn("File-based database embedded in Docker image (embed_db_file_in_microservice: true).")
            warn("  Data is baked in at build time — rebuild the image to pick up any DB changes.")
        else:
            info("File-based database will be mounted at runtime via Docker volume.")
            info(f"  Host directory: {_db_info['host_db_dir']}")
            info(f"  Container path: {_db_info['container_db_dir']}")
            info("  The run_docker_app scripts include the -v mount automatically.")

    # ── Optional: docker build ────────────────────────────────────────────────
    header("Phase 3 - Step 7 - Build Docker Image")
    docker_built = False
    if yn_confirm("Run 'docker build' now?", default=True):
        cmd = ["docker", "build", "--platform", cfg["docker_platform"], "-t", f"{image_name}:{image_tag}", "."]
        info(f"Running: {' '.join(cmd)}")
        if _running_in_docker():
            info(
                "Note: the orm_skyway image's Docker CLI doesn't have buildx installed, "
                "so a 'legacy builder is deprecated' warning may print below. "
                "It's harmless and does not affect the build."
            )
        ret = subprocess.run(cmd, cwd=str(root))
        if ret.returncode == 0:
            info(f"Docker image built successfully: {image_name}:{image_tag}")
            docker_built = True
        else:
            error("docker build failed (see output above).")
    else:
        info("Skipping docker build — run build.cmd / build.sh manually when ready.")

    cfg["_docker_built"] = docker_built

# ==============================================================================
# 11. SUMMARY
# ==============================================================================

def print_summary(cfg: dict, config_path: Path, table_class_map: dict):
    root     = cfg["project_root"]
    rev_file = config_path.with_suffix(".config.revjdx")
    jdx_file = config_path.with_suffix(".config.jdx")
    pkg_rel  = pkg_to_rel(cfg["object_model_package"])

    header("Workflow Complete - Summary")

    rows = [
        ("Project root",              str(root)),
        ("ORM template config",       str(config_path.relative_to(root))),
        ("ORM starting point",        str(rev_file.relative_to(root)) + "  (do not edit)"),
        ("ORM working spec (.jdx)",   str(jdx_file.relative_to(root)) + "  (edit/refine this)"),
        ("Model sources",             str(Path(SRC_DIR) / pkg_rel)),
        ("Compiled classes",          str(Path(BIN_DIR) / pkg_rel)),
        ("JDBC JAR in config/",       str(Path(CONFIG_DIR) / Path(cfg["jdbc_driver_jar"]).name)),
        ("Tables / Classes",          ", ".join(f"{t}->{c}" for t, c in table_class_map.items())),
        ("Docker image",              f"{cfg.get('docker_image_name', '?')}:{cfg.get('docker_image_tag', '1.0')}"),
        ("REST base URL",             f"http://localhost:{cfg.get('gilhari_host_port', 80)}/gilhari/v1/<ClassName>"),
    ]

    if HAS_RICH:
        tbl = Table(show_header=False, show_lines=True)
        tbl.add_column("Key",   style="cyan")
        tbl.add_column("Value", style="white")
        for k, v in rows:
            tbl.add_row(k, v)
        console.print(tbl)
    else:
        for k, v in rows:
            print(f"  {k:28} {v}")




# ==============================================================================
# ARGUMENT PARSER
# ==============================================================================

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="JDX/Gilhari Reverse Engineering Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-f", "--config-file",
                   help="Path to JSON config file (CLI flags override file values)")
    p.add_argument("--project-dir",
                   default=None,
                   help="Project root directory (default: current working directory)")
    p.add_argument("--phase",
                   choices=["1", "3", "1+3", "introspect"],
                   default="1+3",
                   help="Which phase(s) to run: 1=reverse-engineer, 3=Gilhari packaging, 1+3=both, introspect=list tables only (default: 1+3)")
    # Phase 1 settings
    p.add_argument("--jdbc-url",          help="JDBC connection URL")
    p.add_argument("--db-user",           help="Database username")
    p.add_argument("--db-password",       help="Database password")
    p.add_argument("--db-type",           help="DB type (MYSQL/POSTGRES/ORACLE/MSSQL/SQLITE/DB2/SNOWFLAKE/MARIADB/DATABRICKS/SPANNER/COCKROACHDB/YUGABYTE — auto-detected from URL if omitted)")
    p.add_argument("--jdbc-driver-class", help="JDBC driver class name")
    p.add_argument("--jdbc-driver-jar",   help="Path to JDBC driver JAR")
    p.add_argument("--jdbc-driver-lic",   help="Path to an accompanying JDBC driver license file, if the driver "
                                                "needs one (e.g. CData drivers). Auto-detected by default as a "
                                                "same-stem .lic file next to the jar; only set this if your "
                                                "license file doesn't follow that naming convention.")
    p.add_argument("--jx-home",           help="JX_HOME - root of JDX or Gilhari installation")
    p.add_argument("--jdx-dev-bin-path",  help="Optional path to JDX dev build bin/ (prepended to classpath for SDK development testing)")
    p.add_argument("--object-model-package", help="Java package for generated model classes")
    p.add_argument("--reverse-eng-template-config", help="Base name for the reverse-engineering template config file")
    p.add_argument("--db-schema",         help="DB schema/catalog to inspect")
    p.add_argument("--model-overview",    help="One-line object model description for AI/clients")
    p.add_argument("--tables",            help="Comma-separated table list (skips interactive selection)")
    p.add_argument("--skip-reverse-eng",  action="store_true", help="Skip running JDXReverseEngineer")
    p.add_argument("--skip-compile",      action="store_true", help="Skip compiling generated classes")
    p.add_argument("--verbose",           action="store_true", help="Print detailed progress (commands, file writes, class mappings)")
    p.add_argument("--yes", "-y",         action="store_true", help="Auto-accept all confirmation prompts (non-interactive / CI mode)")
    # Phase 3 settings
    p.add_argument("--docker-image-name", help="Docker image name (default: derived from config-name)")
    p.add_argument("--docker-image-tag",  help="Docker image tag (default: 1.0)")
    p.add_argument("--gilhari-host-port",      help="Host port for Gilhari REST service (default: 80)")
    p.add_argument("--docker-platform",   help="Docker target platform, e.g. linux/amd64 or linux/arm64 "
                                                "(default: auto-detected from host architecture)")
    p.add_argument("--docker-hostname", help="Fixed hostname to assign the container via 'docker run "
                                              "--hostname' (default: the image name). For CData's Excel "
                                              "driver, confirmed necessary (2026-07-14) AND must be set to "
                                              "your actual host machine's real hostname (Windows: run "
                                              "`hostname` or check %COMPUTERNAME%) — not an arbitrary fixed "
                                              "value. Required together with --docker-mac-address below.")
    p.add_argument("--docker-mac-address", help="Fixed MAC address to assign the container via 'docker run "
                                                 "--mac-address' (e.g. 02:42:ac:11:00:02). Without a fixed "
                                                 "value, Docker assigns a new random MAC to the container on "
                                                 "every run. For CData's Excel driver, confirmed necessary "
                                                 "(2026-07-14) AND must be set to your actual host machine's "
                                                 "real MAC address (Windows: run `getmac /v`) — not an "
                                                 "arbitrary fixed value. Required together with "
                                                 "--docker-hostname above.")
    return p


# ==============================================================================
# PHASE 1 — Reverse-engineer database schema into JDX object model
# ==============================================================================

def _validate_table_selection(tables_arg: str, all_tables: list) -> list:
    """
    Parse a comma-separated table list (from --tables or config 'tables' key),
    validate each name against the DB's actual table list, and handle any
    unrecognised names interactively before returning the final selection.
    """
    # "all" is a special token meaning select every available table,
    # but only when it is the sole value (not mixed with table names like "all,T1,T2").
    # If mixed, "all" is treated as a literal table name and looked up normally.
    _tokens = [t.strip() for t in tables_arg.split(",") if t.strip()]
    if len(_tokens) == 1 and _tokens[0].lower() == "all":
        # Filter out JDX internal tables, same as select_tables()
        JDX_INTERNAL = {"jdxmetadata", "jdxsequence", "jdxtestconnection"}
        def _bare(name): return name.split(".")[-1].lower()
        result = [t for t in all_tables if _bare(t) not in JDX_INTERNAL]
        info(f"tables='all': selecting all {len(result)} user table(s).")
        return result

    all_lower = {t.lower(): t for t in all_tables}  # case-insensitive lookup

    def _resolve(names_str):
        names = [n.strip() for n in names_str.split(",") if n.strip()]
        valid, invalid = [], []
        for n in names:
            if n.lower() in all_lower:
                valid.append(all_lower[n.lower()])  # use DB's actual casing
            else:
                invalid.append(n)
        return valid, invalid

    valid, invalid = _resolve(tables_arg)

    if not invalid:
        info(f"Using pre-selected tables: {', '.join(valid)}")
        return valid

    # Some names not found — show the problem and offer recovery options
    while True:
        print()
        warn(f"The following table name(s) were not found in the database: {', '.join(invalid)}")
        if valid:
            info(f"Valid table(s) from your list: {', '.join(valid)}")
        if valid:
            print(f"  [C] Continue with {', '.join(valid)}")
        else:
            print("  [C] Continue  (no valid tables — not available)")
        print("  [S] Show all available tables, then re-enter")
        print("  [R] Re-enter the table list directly")
        print("  [A] Abort")
        choice = ask("Your choice [C/S/R/A]", "R" if not valid else "C").strip().upper()
        if choice == "A":
            info("Aborted. Please correct the table names in your config file or --tables flag.")
            sys.exit(0)
        elif choice == "C" and valid:
            return valid
        elif choice == "C" and not valid:
            warn("No valid tables to continue with. Please choose S, R, or A.")
        elif choice == "S":
            # Show the full table list and let the user pick interactively
            info("Showing all available tables — select the ones you want:")
            picked = select_tables(list(all_lower.values()))
            if picked:
                return picked
        elif choice == "R":
            new_input = ask("Enter table names (comma-separated)", None) or ""
            if not new_input.strip():
                warn("No tables entered. Please try again.")
                continue
            valid, invalid = _resolve(new_input)
            if not invalid:
                return valid
            # Loop back to show remaining invalid names


CREATE_JDXMETADATA_TABLE_JAVA = """\
import java.sql.*;

public class CreateJdxMetadataHelper {
    public static void main(String[] args) throws Exception {
        String url    = args[0];
        String user   = args[1];
        String pass   = args[2];

        Connection con = DriverManager.getConnection(url, user, pass);
        // Always use a metadata existence check rather than
        // CREATE TABLE IF NOT EXISTS: some JDBC drivers (e.g. CData's Excel
        // driver, which maps CREATE TABLE to creating a new sheet) don't
        // reliably support that syntax, while a plain existence check works
        // universally regardless of driver SQL dialect support.
        java.sql.ResultSet rs = con.getMetaData().getTables(
            null, null, "JDXMetadata", new String[]{"TABLE"});
        boolean exists = rs.next();
        rs.close();
        if (!exists) {
            con.createStatement().executeUpdate(
                "CREATE TABLE JDXMetadata (" +
                "jdxORMId varchar(80), " +
                "jdxTimestamp varchar(80), " +
                "jdxMetaVersionId varchar(80), " +
                "jdxMetaFileName varchar(80), " +
                "jdxMetaInfo LONGTEXT)");
            System.out.println("JDXMetadata table created.");
        } else {
            System.out.println("JDXMetadata table already exists.");
        }
        con.close();
    }
}
"""


def ensure_jdxmetadata_table_excel(cfg: dict):
    """
    Excel/CData only. Pre-creates an empty JDXMetadata table (via a direct
    JDBC CREATE TABLE, executed through the CData driver itself — which maps
    it to creating a new sheet) before JDX or Gilhari ever connects.

    This follows the officially documented approach for using JDX/Gilhari
    against a legacy database with existing data (Gilhari_README.pdf,
    "Using Legacy Data in an Existing Database"): the mere *existence* of a
    JDXMetadata table, empty or not, tells JDX the database has already been
    initialized, so it skips its normal behavior of dropping and recreating
    the mapped tables on first connection. Column types (varchar(80) /
    LONGTEXT for jdxMetaInfo) match jdxMetadata_Access.jdx, which is also
    now used as JDX_METADATA_FILE for Excel connections (see url_db_type
    handling in collect_inputs and the _METADATA_JDX lookup).

    Must run BEFORE the first list_tables_via_java() call in run_phase1, so
    the freshly created table is visible in that table listing (and
    therefore auto-excluded from table selection like any other JDX-internal
    table) — and, more importantly, before Gilhari's own first connection in
    a later phase, since that appears to be where the reported DROP TABLE
    against a user sheet actually originated (JDX's Phase 1 -metaForceCreate
    tool only ever touches JDXMetadata/JDXSequence, confirmed separately in
    ensure_jdxmetadata_via_jdxschema — the destructive behavior described in
    the README matches Gilhari's runtime schema-init on first connection,
    not the Phase 1 CLI tool).

    Non-fatal if the helper fails to compile/run for any reason — falls back
    to the documented manual fix (run the CREATE TABLE by hand, or via any
    SQL client that can reach the workbook through the CData driver) rather
    than blocking Phase 1.
    """
    if cfg.get("url_db_type") != "EXCEL":
        return

    header("Phase 1 - Step 4b - Excel: Pre-create JDXMetadata Table")

    tmp = cfg["project_root"] / ".tmp_helper"
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        src = tmp / "CreateJdxMetadataHelper.java"
        src.write_text(CREATE_JDXMETADATA_TABLE_JAVA, encoding="utf-8")

        driver_jar = cfg["jdbc_driver_jar"]
        cp = SEP.join([str(tmp), driver_jar])

        ret = subprocess.run(["javac", "-cp", cp, str(src)],
                             capture_output=True, text=True)
        if ret.returncode != 0:
            warn("Could not compile the JDXMetadata pre-create helper class.")
            warn(ret.stderr)
            warn("Falling back to the manual fix: run this SQL by hand against "
                 "the workbook (e.g. via any client using the CData driver) "
                 "before re-running if Phase 1 or Gilhari startup drops a sheet:")
            warn("  CREATE TABLE JDXMetadata (jdxORMId varchar(80), jdxTimestamp "
                 "varchar(80), jdxMetaVersionId varchar(80), jdxMetaFileName "
                 "varchar(80), jdxMetaInfo LONGTEXT)")
            return

        # Use effective_jdbc_url so any schema-qualification is honoured,
        # consistent with ensure_jdxtestconnection.
        _url = cfg.get("effective_jdbc_url") or cfg["jdbc_url"]
        cmd = ["java", "-cp", cp, "CreateJdxMetadataHelper",
               _url, cfg["db_user"], cfg["db_password"]]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            warn("Could not pre-create the JDXMetadata table.")
            warn(ret.stderr)
            warn("Falling back to the manual fix: run this SQL by hand against "
                 "the workbook before re-running:")
            warn("  CREATE TABLE JDXMetadata (jdxORMId varchar(80), jdxTimestamp "
                 "varchar(80), jdxMetaVersionId varchar(80), jdxMetaFileName "
                 "varchar(80), jdxMetaInfo LONGTEXT)")
            return
        info(ret.stdout.strip() if ret.stdout else "")
    finally:
        if tmp.exists():
            shutil.rmtree(str(tmp))
            verbose_info("Cleaned up .tmp_helper/ directory (JDXMetadata pre-create step).")


def run_phase1(cfg: dict, args) -> tuple:
    """
    Runs steps 1a-1g:
      1a. Copy JDBC driver JAR to config/
      1b. Create reverse-engineering template .config
      1c. Write helper scripts (setEnvironment, compile, JDXDemo, JDXReverseEngineer)
      1d. Run JDXReverseEngineer -> .java files + .revjdx
      1e. Copy .revjdx -> .jdx (working editable ORM spec)
      1f. Compile generated model classes
      1g. Create JDXMetadata table if absent (requires compiled classes)

    Returns (config_path, table_class_map).
    """
    # Select tables
    header("Phase 1 - Step 5 - Select Tables to Expose")

    # Excel/CData: pre-create an empty JDXMetadata table via JDBC before we
    # even list tables, so JDX/Gilhari see the workbook as already-initialized
    # and the table itself is naturally excluded from selection like other
    # JDX-internal tables (see select_tables()'s JDX_INTERNAL filtering).
    ensure_jdxmetadata_table_excel(cfg)

    # List tables from the database
    all_tables = list_tables_via_java(cfg)
    if not all_tables:
        error("No tables found. Check your connection and schema settings.")
        sys.exit(1)
    info(f"Found {len(all_tables)} table(s) in the database.")

    if args.tables:
        selected_tables = _validate_table_selection(args.tables, all_tables)
    else:
        selected_tables = select_tables(all_tables)

    # Review / rename class names
    table_class_map = review_class_names(selected_tables)

    # 1b - generate template config in config/
    config_path = generate_template_config(cfg, table_class_map)

    # 1a - copy JDBC JAR into config/
    header("Phase 1 - Step 8 - Copy JDBC Driver JAR")
    copy_jdbc_jar_to_config(cfg)

    # FA1: if the originally-configured host_jdbc_driver_jar doesn't actually
    # exist on this host (e.g. it was a container-only/bundled path, or never
    # configured at all), fall back to the copy that was just placed in
    # config/ above — that's already on the host via the project mount, and
    # setEnvironment.bat/.sh resolve relative paths from the project root.
    # This matters for JDXDemo.bat/.sh, which run on the host, not in-container.
    if _running_in_docker():
        _host_driver = cfg.get("host_jdbc_driver_jar") or ""
        if not _host_driver or not Path(_host_driver).is_file():
            _fallback = f"{CONFIG_DIR}/{Path(cfg['jdbc_driver_jar']).name}"
            verbose_info(f"host_jdbc_driver_jar not found on host — using {_fallback} for setEnvironment scripts.")
            cfg["host_jdbc_driver_jar"] = _fallback

    # 1c - write helper scripts
    header("Phase 1 - Step 9 - Generate Helper Scripts")
    write_helper_scripts(cfg, config_path, list(table_class_map.values()))

    # 1d - run JDXReverseEngineer
    header("Phase 1 - Step 10 - Run JDXReverseEngineer")
    jdx_path = None
    if args.skip_reverse_eng:
        warn("Skipping JDXReverseEngineer (--skip-reverse-eng flag set).")
    else:
        if yn_confirm("Run JDXReverseEngineer now?", default=True):
            run_reverse_engineer(cfg, config_path)
            # 1e - copy .revjdx -> .jdx
            jdx_path = copy_revjdx_to_jdx(config_path)
            cfg["jdx_path"] = jdx_path
        else:
            warn("Skipping. Run JDXReverseEngineer.bat / .sh manually later.")
            warn("Then copy the .revjdx to a .jdx file for downstream use.")

    # 1f - compile generated model classes
    header("Phase 1 - Step 11 - Compile Generated Model Classes")
    compiled = False
    if args.skip_compile:
        warn("Skipping compilation (--skip-compile flag set).")
    else:
        if yn_confirm("Compile generated Java classes now?", default=True):
            compile_classes(cfg)
            compiled = True
        else:
            warn("Skipping. Run compile.bat / compile.sh manually later.")

    # 1g - pre-create JDXTestConnection, then create JDXMetadata if absent.
    # JDXTestConnection must exist before JDXSchema -metaForceCreate runs to avoid
    # a PostgreSQL transaction-abort bug in JDX (safe no-op for all other DB types).
    # JDXMetadata creation must run after compilation — JDXSchema validates the
    # mapping file on startup and requires compiled .class files in bin/.
    # Only attempted if reverse-engineering and compilation both ran in this session.
    if jdx_path and compiled:
        ensure_jdxtestconnection(cfg)
        ensure_jdxmetadata_via_jdxschema(cfg, jdx_path, all_tables)
    elif jdx_path and not compiled:
        warn("Skipping JDXMetadata creation — compiled classes required but compilation was skipped.")
        warn("Run compile.bat / compile.sh, then re-run Phase 1 or call JDXSchema -metaForceCreate manually.")

    # FA1: config/*.config, *.revjdx, *.jdx must keep working directly on the
    # host (JDXDemo can't run inside this container at all). All live
    # in-container operations that needed the Docker-internal URL embedded in
    # these files (reverse engineering above, and JDXMetadata creation just
    # above) are now done for this run — safe to restore the host-facing URL.
    if jdx_path:
        revert_docker_url_in_host_artifacts(cfg, config_path)

    return config_path, table_class_map



# ==============================================================================
# B1. PREFLIGHT VALIDATION
# ==============================================================================

def validate_inputs(cfg: dict, phase: str):
    """
    Run preflight checks before any files are written or DB connections made.
    Checks: required tools on PATH, SDK jars present, JDBC driver file exists,
    docker available (Phase 3). Prints a clear actionable message for each failure.
    """
    _preflight_header = ("Preflight Validation" if phase == "3"
                         else "Phase 1 - Step 4 - Preflight Validation")
    header(_preflight_header)
    errors = []

    # ── java / javac on PATH ──────────────────────────────────────────────────
    for tool in ("java", "javac"):
        try:
            r = subprocess.run([tool, "-version"], capture_output=True, text=True)
            ver = (r.stdout or r.stderr).strip().split("\n")[0]
            verbose_info(f"  {tool}: {ver}")
        except FileNotFoundError:
            errors.append(f"'{tool}' not found on PATH. Please install a JDK and add it to PATH.")

    # ── JX_HOME jars (Phase 1 only) ───────────────────────────────────────────
    if phase in ("1", "1+3") and cfg.get("jx_home"):
        jx = Path(cfg["jx_home"])
        for jar in ("libs/jxclasses.jar", "libs/jdxtools.jar"):
            p = jx / jar
            if not p.exists():
                errors.append(f"JDX jar not found: {p}\n"
                               "  Check that jx_home points to the root of your Gilhari/JDX SDK.")

    # ── JDBC driver JAR ───────────────────────────────────────────────────────
    if cfg.get("jdbc_driver_jar"):
        driver_path = Path(cfg["jdbc_driver_jar"])
        if not driver_path.exists():
            errors.append(f"JDBC driver JAR not found: {driver_path}\n"
                           "  Check the jdbc_driver_jar setting in your config file.")

    # ── docker on PATH (Phase 3 only) ─────────────────────────────────────────
    if phase in ("3", "1+3"):
        try:
            r = subprocess.run(["docker", "info"], capture_output=True, text=True)
            if r.returncode != 0:
                errors.append("Docker daemon is not running. Please start Docker Desktop "
                               "or the Docker daemon before running Phase 3.")
            else:
                verbose_info("  docker: daemon is running")
        except FileNotFoundError:
            errors.append("'docker' not found on PATH. Please install Docker.")

    # ── project dir writable ──────────────────────────────────────────────────
    root = cfg.get("project_root", Path.cwd())
    try:
        test_file = root / ".orm_preflight_test"
        test_file.write_text("ok")
        test_file.unlink()
    except OSError:
        errors.append(f"Project directory is not writable: {root}")

    if errors:
        print()
        error("Preflight validation failed. Please fix the following issues before continuing:")
        for i, msg in enumerate(errors, 1):
            print(f"  {i}. {msg}")
        sys.exit(1)
    else:
        info("Preflight checks passed.")



# ==============================================================================
# C2. INTROSPECT PHASE
# ==============================================================================

def run_phase_introspect(cfg: dict):
    """
    --phase introspect: connect to the database, list all available tables,
    and print their names. Read-only — no files written, no schema changes.
    """
    header("Phase introspect - List All Available Database Tables")
    all_tables = list_tables_via_java(cfg)
    if not all_tables:
        error("No tables found. Check your connection and schema settings.")
        sys.exit(1)

    JDX_INTERNAL = {"jdxmetadata", "jdxsequence", "jdxtestconnection"}
    def _bare(name): return name.split(".")[-1].lower()
    user_tables   = [t for t in all_tables if _bare(t) not in JDX_INTERNAL]
    internal      = [t for t in all_tables if _bare(t) in JDX_INTERNAL]

    info(f"Found {len(all_tables)} table(s) in the database "
         f"({len(user_tables)} user, {len(internal)} JDX internal).")

    if HAS_RICH:
        from rich.table import Table as RichTable
        tbl = RichTable(title="Available Tables", show_lines=True)
        tbl.add_column("#",          style="cyan", justify="right")
        tbl.add_column("Table Name", style="white")
        tbl.add_column("Type",       style="dim")
        for i, t in enumerate(all_tables, 1):
            kind = "JDX internal" if t.lower() in JDX_INTERNAL else "user"
            tbl.add_row(str(i), t, kind)
        console.print(tbl)
    else:
        print()
        for i, t in enumerate(all_tables, 1):
            kind = " (JDX internal)" if t.lower() in JDX_INTERNAL else ""
            print(f"  {i:3}. {t}{kind}")
        print()

    info("Introspect complete. No files were written or modified.")



# ==============================================================================
# F2. ORMCP CONNECTION GUIDE
# ==============================================================================

def write_ormcp_guide(cfg: dict, class_names: list):
    """
    Generate connectORMCP.md — a tailored guide for connecting ORMCP to the
    running Gilhari microservice, with all project-specific values filled in.
    """
    root        = cfg["project_root"]
    image_name  = cfg["docker_image_name"]
    image_tag   = cfg.get("docker_image_tag", "1.0")
    host_port   = cfg.get("gilhari_host_port", 80)
    base_url    = f"http://localhost:{host_port}/gilhari/v1/"
    server_name = f"{image_name}-ormcp"
    overview    = cfg.get("model_overview", "")

    # Example class names for sample queries (up to 2)
    sample_classes = class_names[:2]
    example_queries = "\n".join(
        f'- *"Show me all {cls} objects"*' for cls in sample_classes
    )
    if class_names:
        example_queries += f'\n- *"How many {class_names[0]} objects are there?"*'
        if len(class_names) > 1:
            example_queries += f'\n- *"Get the first 5 {class_names[1]} objects"*'

    guide = f"""# Connecting ORMCP to {image_name}

Generated by orm_skyway.py

{f"**Object model:** {overview}" if overview else ""}

ORMCP (ORM Model Context Protocol) connects your AI agent to the running
Gilhari microservice so it can query and interact with your data through
natural language.

---

## Prerequisites

- The `{image_name}` Gilhari microservice must be running:
  ```
  run_docker_app.cmd    # Windows
  ./run_docker_app.sh   # macOS / Linux
  ```
- ORMCP Server must be installed (see below).

---

## Step 1 — Install ORMCP Server

```bash
pip install ormcp-server
```

No account, token, or beta-access request is needed — this installs from public PyPI directly.

> **macOS note — virtual environment location:** Do not create your venv inside `~/Desktop/` or `~/Documents/`. macOS restricts access to these folders for apps without Full Disk Access, causing Claude Desktop to throw a `PermissionError` on `pyvenv.cfg`. Use an unrestricted location instead, e.g. `~/.ormcp-venv`.

**If you have an existing Gemfury token** from an earlier beta install, it still works, but it's no longer required.

---

## Step 2 — Configure your AI client

### Claude Desktop

Add the following to `claude_desktop_config.json`:

**Windows:** `%APPDATA%\\Claude\\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{{
  "mcpServers": {{
    "{server_name}": {{
      "command": "ormcp-server",
      "args": [],
      "env": {{
        "GILHARI_BASE_URL": "{base_url}",
        "MCP_SERVER_NAME": "{server_name}",
        "GILHARI_NAME": "{image_name}",
        "GILHARI_IMAGE": "{image_name}:{image_tag}",
        "GILHARI_PORT": "{host_port}",
        "READONLY_MODE": "True"
      }}
    }}
  }}
}}
```

Claude Desktop starts the ORMCP server automatically — no separate terminal needed.

> **Windows note:** If `ormcp-server` is not found, use the full path instead:
> `"command": "C:\\Users\\<YourUsername>\\AppData\\Roaming\\Python\\Python313\\Scripts\\ormcp-server.exe"`
> Run `where ormcp-server` in a command prompt to find the exact path.

### Other MCP clients (Gemini CLI, OpenAI GPTs, etc.)

Set these environment variables before starting ORMCP:
```bash
# macOS / Linux
export GILHARI_BASE_URL="{base_url}"
export MCP_SERVER_NAME="{server_name}"
export GILHARI_NAME="{image_name}"
export GILHARI_IMAGE="{image_name}:{image_tag}"
export GILHARI_PORT="{host_port}"
export READONLY_MODE="True"

# Windows (Command Prompt)
set GILHARI_BASE_URL={base_url}
set MCP_SERVER_NAME={server_name}
set GILHARI_NAME={image_name}
set GILHARI_IMAGE={image_name}:{image_tag}
set GILHARI_PORT={host_port}
set READONLY_MODE=True
```

Then start the server: `ormcp-server`

See the [ORMCP documentation](https://github.com/SoftwareTree/ormcp-docs) for
client-specific configuration (Gemini CLI, OpenAI GPTs, HTTP mode).

> **HTTP mode:** ORMCP can also run as an HTTP server, making it accessible
> from other machines, mobile devices, and any HTTP-capable client — not just
> local AI desktop apps. Start with `ormcp-server --http` and point clients
> at `http://<host>:<port>/`. See the ORMCP documentation for details.

---

## Step 3 — Example interactions

Once connected, try asking your AI agent:

{example_queries}
- *"Give me a summary of the object model"*
- *"What classes / types does this service expose?"*

---

## ORMCP environment variables reference

| Variable | Value for this project | Description |
|---|---|---|
| `GILHARI_BASE_URL` | `{base_url}` | Base URL of the running Gilhari microservice |
| `MCP_SERVER_NAME` | `{server_name}` | Name shown in AI client tool lists |
| `GILHARI_NAME` | `{image_name}` | Container name for auto-start |
| `GILHARI_IMAGE` | `{image_name}:{image_tag}` | Docker image for auto-start |
| `GILHARI_PORT` | `{host_port}` | Port for auto-start |
| `READONLY_MODE` | `True` (default) | Set `False` to allow write operations (create, update, delete) |
| `GILHARI_TIMEOUT` | `30` (default) | API timeout in seconds |
| `LOG_LEVEL` | `INFO` (default) | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

---

## Further reading

- [ORMCP documentation](https://github.com/SoftwareTree/ormcp-docs)
- [Gilhari SDK](https://softwaretree.com/v1/products/gilhari/gilhari_introduction.php)
"""

    guide_path = root / "connectORMCP.md"
    guide_path.write_text(guide)
    info("ORMCP connection guide written: connectORMCP.md")


# ==============================================================================
# PHASE 3 — Package model into a Gilhari RESTful microservice Docker image
# ==============================================================================

def _parse_jdx_for_curl(jdx_path: Path) -> dict:
    """Parse CLASS blocks from a .jdx file for curl write command generation.
    Returns dict of {ClassName: {attribs, rdbms_generated, pk}} for top-level
    classes only (not COLLECTION_CLASS entries).
    """
    import re
    classes = {}
    current = None
    try:
        text = jdx_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^CLASS \.\s*(\w+)\s+TABLE', line)
        if m:
            current = m.group(1)
            classes[current] = {"attribs": {}, "rdbms_generated": set(), "pk": []}
            continue
        if current is None:
            continue
        if line.startswith(';'):
            current = None
        elif m2 := re.match(r'VIRTUAL_ATTRIB\s+(\w+)\s+ATTRIB_TYPE\s+(\S+)', line):
            classes[current]["attribs"][m2.group(1)] = m2.group(2)
        elif m3 := re.match(r'PRIMARY_KEY\s+(.*)', line):
            classes[current]["pk"] = m3.group(1).split()
        elif m4 := re.match(r'RDBMS_GENERATED\s+(.*)', line):
            classes[current]["rdbms_generated"].update(m4.group(1).split())
    return classes


def _curl_placeholder(type_str: str) -> str:
    """Return a sensible JSON placeholder value for a given Java type string."""
    t = type_str.lower()
    if "string"    in t: return '"sample_value"'
    if "bigdecimal"in t: return '0.00'
    if "double"    in t: return '0.0'
    if "float"     in t: return '0.0'
    if "long"      in t: return '1'
    if "int"       in t: return '1'
    if "boolean"   in t: return 'true'
    if "timestamp" in t: return '"2026-01-01T00:00:00"'
    if "date"      in t: return '"2026-01-01"'
    return '"value"'


def write_curl_write_scripts(cfg: dict, class_names: list):
    """
    Generate sampleCurlWriteCommands.cmd/.sh — commented-out write operation examples.

    All curl commands are REM'd / #-commented to prevent accidental execution.
    Users must deliberately uncomment and replace placeholder values before running.
    RDBMS_GENERATED attributes are excluded from POST examples since the database
    generates those values automatically.
    """
    root  = cfg["project_root"]
    port  = cfg.get("gilhari_host_port", 80)

    # Try to parse the .jdx file for attribute info
    jdx_path = cfg.get("jdx_path")
    if jdx_path is None:
        # Phase 3 only — find the .jdx from config
        rev_cfg = cfg.get("reverse_eng_template_config", "reverse_eng_template")
        jdx_path = root / CONFIG_DIR / f"{rev_cfg}.config.jdx"
    jdx_classes = _parse_jdx_for_curl(Path(jdx_path)) if jdx_path else {}

    def _curl_placeholder_cmd(type_str: str) -> str:
        """Return a JSON placeholder value with cmd-style escaping for string values."""
        t = type_str.lower()
        if "string"    in t: return '\\\\\\"sample_value\\\\\\"'
        if "bigdecimal"in t: return '0.00'
        if "double"    in t: return '0.0'
        if "float"     in t: return '0.0'
        if "long"      in t: return '1'
        if "int"       in t: return '1'
        if "boolean"   in t: return 'true'
        if "timestamp" in t: return '\\\\\\"2026-01-01T00:00:00\\\\\\"'
        if "date"      in t: return '\\\\\\"2026-01-01\\\\\\"'
        return '\\\\\\"value\\\\\\"'

    def _post_body(cls):
        """Build a POST entity body excluding RDBMS_GENERATED attributes (cmd format)."""
        info = jdx_classes.get(cls, {})
        attribs = info.get("attribs", {})
        rdbms_gen = info.get("rdbms_generated", set())
        post_attribs = {k: v for k, v in attribs.items() if k not in rdbms_gen}
        if not post_attribs:
            return '{\\\\\\"field1\\\\\\": \\\\\\"value1\\\\\\"}'
        pairs = ", ".join(f'\\\\\\"{ k}\\\\\\": {_curl_placeholder_cmd(v)}' for k, v in post_attribs.items())
        return '{' + pairs + '}'

    def _post_body_sh(cls):
        info = jdx_classes.get(cls, {})
        attribs = info.get("attribs", {})
        rdbms_gen = info.get("rdbms_generated", set())
        post_attribs = {k: v for k, v in attribs.items() if k not in rdbms_gen}
        if not post_attribs:
            return '{"field1": "value1"}'
        pairs = ", ".join(f'"{k}": {_curl_placeholder(v)}' for k, v in post_attribs.items())
        return '{' + pairs + '}'

    def _pk_filter(cls, cmd=True):
        """Build a sample filter using the first PK attribute."""
        info = jdx_classes.get(cls, {})
        pk = info.get("pk", [])
        attribs = info.get("attribs", {})
        if pk:
            pk_attr = pk[0]
            pk_type = attribs.get(pk_attr, "java.lang.String")
            pk_val  = _curl_placeholder(pk_type).strip('"') or "1"
            return f"{pk_attr}='{pk_val}'" if "string" in pk_type.lower() else f"{pk_attr}={pk_val}"
        return "field1='value1'"

    def _put_body(cls, cmd=True):
        info = jdx_classes.get(cls, {})
        attribs = info.get("attribs", {})
        if not attribs:
            return '{\\\\\\"field1\\\\\\": \\\\\\"value1\\\\\\"}' if cmd else '{"field1": "value1"}'
        if cmd:
            pairs = ", ".join(f'\\\\\\"{ k}\\\\\\": {_curl_placeholder_cmd(v)}' for k, v in attribs.items())
        else:
            pairs = ", ".join(f'"{k}": {_curl_placeholder(v)}' for k, v in attribs.items())
        return '{' + pairs + '}'

    def _patch_new_values(cls, cmd=True):
        info = jdx_classes.get(cls, {})
        attribs = info.get("attribs", {})
        rdbms_gen = info.get("rdbms_generated", set())
        pk = set(info.get("pk", []))
        update_attribs = {k: v for k, v in attribs.items()
                         if k not in rdbms_gen and k not in pk}
        if not update_attribs:
            update_attribs = attribs
        first_k, first_v = next(iter(update_attribs.items()))
        if cmd:
            return f'[\\\\\\"{ first_k}\\\\\\", {_curl_placeholder_cmd(first_v)}]'
        else:
            return f'["{first_k}", {_curl_placeholder(first_v)}]'

    def _cmd():
        lines = [
            "REM sampleCurlWriteCommands.cmd — Example write operations (POST, PUT, PATCH, DELETE) for this Gilhari service",
            "REM Generated by orm_skyway.py",
            "REM",
            "REM All curl commands below are commented out (REM) to prevent accidental",
            "REM execution. To use a command, remove the REM prefix on the curl line",
            "REM and replace placeholder values with real ones.",
            "REM Each command WILL modify data in your database.",
            "REM For read-only (GET) operations, use sampleCurlCommands.cmd instead.",
            "REM",
            f"SET BASE_URL=http://localhost:{port}/gilhari/v1",
            "",
        ]
        for cls in class_names:
            rdbms_gen = jdx_classes.get(cls, {}).get("rdbms_generated", set())
            lines += [
                f"REM --- {cls} ---",
                "",
                f"REM POST: Insert a new {cls} object",
            ]
            if rdbms_gen:
                lines.append(f"REM Note: {', '.join(sorted(rdbms_gen))} {'is' if len(rdbms_gen)==1 else 'are'} auto-generated (RDBMS_GENERATED) — do not supply {'it' if len(rdbms_gen)==1 else 'them'}")
            lines += [
                f'REM curl.exe -s -X POST %BASE_URL%/{cls} -H "Content-Type: application/json" -d "{{\\\"entity\\\": {_post_body(cls)}}}"',
                "",
                f"REM PUT: Update a specific {cls} object (supply primary key + all attributes)",
                f'REM curl.exe -s -X PUT %BASE_URL%/{cls}/updateEntity -H "Content-Type: application/json" -d "{{\\\"entity\\\": {_put_body(cls, cmd=True)}}}"',
                "",
                f"REM PATCH: Bulk-update {cls} objects matching a filter (returns count of updated objects)",
                f'REM curl.exe -s -X PATCH "%BASE_URL%/{cls}?filter={_pk_filter(cls)}" -H "Content-Type: application/json" -d "{{\\\"newValues\\\": {_patch_new_values(cls, cmd=True)}}}"',
                "",
                f"REM DELETE: Delete {cls} objects matching a filter",
                f'REM curl.exe -s -X DELETE "%BASE_URL%/{cls}?filter={_pk_filter(cls)}"',
                "",
            ]
        return "\r\n".join(lines) + "\r\n"

    def _sh():
        lines = [
            "#!/bin/bash",
            "# sampleCurlWriteCommands.sh — Example write operations (POST, PUT, PATCH, DELETE) for this Gilhari service",
            "# Generated by orm_skyway.py",
            "#",
            "# All curl commands below are commented out (#) to prevent accidental",
            "# execution. To use a command, remove the # prefix on the curl line",
            "# and replace placeholder values with real ones.",
            "# Each command WILL modify data in your database.",
            "# For read-only (GET) operations, use sampleCurlCommands.sh instead.",
            "#",
            f'BASE_URL="http://localhost:{port}/gilhari/v1"',
            "",
        ]
        for cls in class_names:
            rdbms_gen = jdx_classes.get(cls, {}).get("rdbms_generated", set())
            lines += [
                f"# --- {cls} ---",
                "",
                f"# POST: Insert a new {cls} object",
            ]
            if rdbms_gen:
                lines.append(f"# Note: {', '.join(sorted(rdbms_gen))} {'is' if len(rdbms_gen)==1 else 'are'} auto-generated (RDBMS_GENERATED) — do not supply {'it' if len(rdbms_gen)==1 else 'them'}")
            lines += [
                f"# curl -s -X POST \"$BASE_URL/{cls}\" -H \"Content-Type: application/json\" -d '{{\"entity\": {_post_body_sh(cls)}}}'",
                "",
                f"# PUT: Update a specific {cls} object (supply primary key + all attributes)",
                f"# curl -s -X PUT \"$BASE_URL/{cls}/updateEntity\" -H \"Content-Type: application/json\" -d '{{\"entity\": {_put_body(cls, cmd=False)}}}'",
                "",
                f"# PATCH: Bulk-update {cls} objects matching a filter (returns count of updated objects)",
                f"# curl -s -X PATCH \"$BASE_URL/{cls}?filter={_pk_filter(cls)}\" -H \"Content-Type: application/json\" -d '{{\"newValues\": {_patch_new_values(cls, cmd=False)}}}'",
                "",
                f"# DELETE: Delete {cls} objects matching a filter",
                f"# curl -s -X DELETE \"$BASE_URL/{cls}?filter={_pk_filter(cls)}\"",
                "",
            ]
        return "\n".join(lines) + "\n"

    cmd_path = root / "sampleCurlWriteCommands.cmd"
    cmd_path.write_text(_cmd(), encoding="utf-8")

    sh_path = root / "sampleCurlWriteCommands.sh"
    write_sh(sh_path, _sh())

    info("Sample curl write command scripts written: sampleCurlWriteCommands.cmd / sampleCurlWriteCommands.sh")


def write_curl_scripts(cfg: dict, class_names: list):
    """
    Generate sampleCurlCommands.cmd (Windows) and sampleCurlCommands.sh (macOS/Linux).
    Covers: health check, getObjectModelSummary, and deep + shallow GET for the
    first two classes. maxObjects=5 limits output. curl.log is truncated at the start.
    """
    root    = cfg["project_root"]
    port    = cfg.get("gilhari_host_port", 80)
    max_obj = 5
    sample  = class_names[:2]

    def _cmd():
        lines = [
            "REM Sample curl commands for the Gilhari microservice.",
            "REM Generated by orm_skyway.py",
            "REM",
            "REM GET commands use deep=true (includes related objects) and maxObjects=5.",
            "REM Use deep=false to exclude related objects (useful for complex object graphs).",
            "REM Remove maxObjects to retrieve all qualifying objects,",
            "REM or change it to a different value (-1 to get all qualifying objects).",
            "REM",
            "REM Responses are recorded in curl.log.",
            "REM",
            "REM You may optionally specify a port as the first argument:",
            "REM   sampleCurlCommands 8899",
            "IF %1.==. GOTO DefaultPort",
            "SET port=%1",
            "GOTO Proceed",
            ":DefaultPort",
            f"SET port={port}",
            "GOTO Proceed",
            ":Proceed",
            "",
            "REM Truncate curl.log at the start so it does not grow across runs",
            "echo. > curl.log",
            "",
            "echo ** BEGIN OUTPUT ** >> curl.log",
            "echo. >> curl.log",
            "",
            "REM -- Health check --",
            "echo ** Health check >> curl.log",
            'curl.exe -s "http://localhost:%port%/gilhari/v1/health/check" | python -m json.tool >> curl.log',
            "echo. >> curl.log",
            "",
            "REM -- Object model summary (plain text response, not JSON) --",
            "echo ** Object model summary >> curl.log",
            'curl.exe -s "http://localhost:%port%/gilhari/v1/getObjectModelSummary/now" >> curl.log',
            "echo. >> curl.log",
            "",
        ]
        for cls in sample:
            lines += [
                f"REM -- GET {cls} objects - deep (includes related objects, up to {max_obj}) --",
                f"echo ** GET {cls} objects (deep) >> curl.log",
                f'curl.exe -s -X GET "http://localhost:%port%/gilhari/v1/{cls}?deep=true&maxObjects={max_obj}" -H "Content-Type: application/json" | python -m json.tool >> curl.log',
                "echo. >> curl.log",
                "",
                f"REM -- GET {cls} objects - shallow (excludes related objects, up to {max_obj}) --",
                f"echo ** GET {cls} objects (shallow) >> curl.log",
                f'curl.exe -s -X GET "http://localhost:%port%/gilhari/v1/{cls}?deep=false&maxObjects={max_obj}" -H "Content-Type: application/json" | python -m json.tool >> curl.log',
                "echo. >> curl.log",
                "",
            ]
        lines += [
            "echo ** END OUTPUT ** >> curl.log",
            "echo. >> curl.log",
            "type curl.log",
        ]
        return "\r\n".join(lines) + "\r\n"

    def _sh():
        lines = [
            "#!/bin/bash",
            "# Sample curl commands for the Gilhari microservice.",
            "# Generated by orm_skyway.py",
            "#",
            "# GET commands use deep=true (includes related objects) and maxObjects=5.",
            "# Use deep=false to exclude related objects (useful for complex object graphs).",
            "# Remove maxObjects to retrieve all qualifying objects,",
            "# or change it to a different value (-1 to get all qualifying objects).",
            "#",
            "# Responses are recorded in curl.log.",
            "#",
            "# You may optionally specify a port as the first argument:",
            "#   ./sampleCurlCommands.sh 8899",
            f'port="${{1:-{port}}}"',
            "",
            "# Truncate curl.log at the start so it does not grow across runs",
            "> curl.log",
            "",
            'echo "** BEGIN OUTPUT **" >> curl.log',
            'echo "" >> curl.log',
            "",
            "# -- Health check --",
            'echo "** Health check" >> curl.log',
            'curl -s "http://localhost:$port/gilhari/v1/health/check" | python3 -m json.tool >> curl.log',
            'echo "" >> curl.log',
            "",
            "# -- Object model summary (plain text response, not JSON) --",
            'echo "** Object model summary" >> curl.log',
            'curl -s "http://localhost:$port/gilhari/v1/getObjectModelSummary/now" >> curl.log',
            'echo "" >> curl.log',
            "",
        ]
        for cls in sample:
            lines += [
                f"# -- GET {cls} objects - deep (includes related objects, up to {max_obj}) --",
                f'echo "** GET {cls} objects (deep)" >> curl.log',
                f'curl -s -X GET "http://localhost:$port/gilhari/v1/{cls}?deep=true&maxObjects={max_obj}" -H "Content-Type: application/json" | python3 -m json.tool >> curl.log',
                'echo "" >> curl.log',
                "",
                f"# -- GET {cls} objects - shallow (excludes related objects, up to {max_obj}) --",
                f'echo "** GET {cls} objects (shallow)" >> curl.log',
                f'curl -s -X GET "http://localhost:$port/gilhari/v1/{cls}?deep=false&maxObjects={max_obj}" -H "Content-Type: application/json" | python3 -m json.tool >> curl.log',
                'echo "" >> curl.log',
                "",
            ]
        lines += [
            'echo "** END OUTPUT **" >> curl.log',
            'echo "" >> curl.log',
            "cat curl.log",
        ]
        return "\n".join(lines) + "\n"

    cmd_path = root / "sampleCurlCommands.cmd"
    cmd_path.write_text(_cmd(), encoding="utf-8")

    sh_path = root / "sampleCurlCommands.sh"
    write_sh(sh_path, _sh())

    info("Sample curl scripts written: sampleCurlCommands.cmd / sampleCurlCommands.sh")
    info("  Run them after starting the service to test some REST APIs.")
    info("  Responses are logged to curl.log.")

    # ── Project .gitignore ────────────────────────────────────────────────
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        driver_jar_name = Path(cfg["jdbc_driver_jar"]).name
        config_name     = cfg["reverse_eng_template_config"]
        gitignore_content = (
            "# Auto-generated by orm_skyway.py\n"
            "# Excludes files that should not be committed to version control.\n"
            "\n"
            "# Compiled Java classes\n"
            "bin/\n"
            "\n"
            "# JDBC driver JAR (large binary, project-specific)\n"
            f"config/{driver_jar_name}\n"
            "\n"
            "# ORM spec files contain DB credentials — do not commit\n"
            f"config/{config_name}.config.jdx\n"
            f"config/{config_name}.config.docker.jdx\n"
            f"config/{config_name}.config.revjdx\n"
            "\n"
            "# curl output log\n"
            "curl.log\n"
            "\n"
            "# Sensitive config (if you store credentials here)\n"
            "orm_skyway_config.json\n"
            "\n"
            "# softwaretree/orm_skyway Docker image: one-time license\n"
            "# acceptance marker -- local/machine-specific, not for VCS\n"
            ".orm_skyway_license_accepted\n"
            "\n"
            "# softwaretree/orm_skyway Docker image: extracted JDX SDK jars +\n"
            "# license, for running JDXDemo.bat/.sh on this host -- regenerable,\n"
            "# host-specific, and includes a license file, so not for VCS\n"
            "jdx_sandbox/\n"
        )
        gitignore_path.write_text(gitignore_content, encoding="utf-8")
        info("Project .gitignore written.")
    else:
        verbose_info("Project .gitignore already exists — not overwritten.")

    # ── Project .gitattributes ───────────────────────────────────────────
    # Ensures correct line endings when generated files are committed to Git
    # from any platform. Shell scripts must have LF endings to run on
    # macOS/Linux; Windows batch files should have CRLF.
    gitattributes_path = root / ".gitattributes"
    if not gitattributes_path.exists():
        gitattributes_content = (
            "# Auto-generated by orm_skyway.py\n"
            "# Enforces correct line endings for generated files in Git.\n"
            "# Shell scripts must have LF endings to run on macOS/Linux.\n"
            "# Windows batch/cmd files should have CRLF.\n"
            "\n"
            "# Shell scripts — always LF\n"
            "*.sh     text eol=lf\n"
            "\n"
            "# Windows scripts — always CRLF\n"
            "*.bat    text eol=crlf\n"
            "*.cmd    text eol=crlf\n"
            "\n"
            "# Text files — LF\n"
            "*.java   text eol=lf\n"
            "*.json   text eol=lf\n"
            "*.md     text eol=lf\n"
            "*.jdx    text eol=lf\n"
            "*.config text eol=lf\n"
            "*.txt    text eol=lf\n"
            "\n"
            "# Binary files — no line ending conversion\n"
            "*.jar    binary\n"
            "*.class  binary\n"
            "*.db     binary\n"
        )
        gitattributes_path.write_text(gitattributes_content, encoding="utf-8")
        info("Project .gitattributes written.")
    else:
        verbose_info("Project .gitattributes already exists — not overwritten.")





def run_phase3(cfg: dict):
    """
    Runs steps 3a-3b:
      3a. Discover compiled classes from bin/, generate classnames_map.json,
          gilhari_service.config, Dockerfile, build/run scripts.
      3b. Optionally run docker build.

    No database connection needed. Reads class list from bin/<package path>/.
    """
    phase_separator("Phase 3 — Gilhari Microservice Packaging")

    header("Phase 3 - Step 1 - Verify Phase 1 Artifacts")
    root        = cfg["project_root"].resolve()
    config_name = cfg["reverse_eng_template_config"]
    jdx_file    = root / CONFIG_DIR / f"{config_name}.config.jdx"
    bin_dir     = root / BIN_DIR

    if not jdx_file.exists():
        error(f"ORM spec not found: {jdx_file.relative_to(root)}")
        error("Has Phase 1 been run? The .jdx file must exist before running Phase 3.")
        sys.exit(1)
    if not bin_dir.exists():
        error(f"bin/ directory not found. Have the Java classes been compiled?")
        sys.exit(1)

    # Phase 3 packages whatever is currently in bin/ as-is — it does not
    # recompile. If src/ was hand-edited during Phase 2 (or a new class
    # added) without a subsequent compile, warn before silently shipping
    # stale/missing .class files into the Docker image.
    _stale = _find_stale_or_uncompiled_java_files(cfg)
    if _stale:
        warn(
            f"{len(_stale)} .java file(s) under {SRC_DIR}/ appear newer than their "
            f"compiled .class file in {BIN_DIR}/ (or have no .class file at all) — "
            "likely hand-edited in Phase 2 without recompiling since:"
        )
        for _f in _stale[:10]:
            warn(f"    {_f.relative_to(root)}")
        if len(_stale) > 10:
            warn(f"    ... and {len(_stale) - 10} more")
        if yn_confirm("Recompile all classes now before continuing with Phase 3?", default=True):
            compile_classes(cfg)
        else:
            warn(f"Continuing with the existing (possibly stale) contents of {BIN_DIR}/.")

    config_path = root / CONFIG_DIR / f"{config_name}.config"

    # 3a - discover classes from bin/ (reflects post-Phase-2 state)
    header("Phase 3 - Step 2 - Discover Compiled Classes")
    class_names = discover_classes_from_bin(cfg)
    if not class_names:
        sys.exit(1)

    write_gilhari_artifacts(cfg, config_path, class_names)

    # Summary for Phase 3
    image_name = cfg.get("docker_image_name") or config_name.lower().replace("_", "-")
    image_tag  = cfg.get("docker_image_tag", "1.0")
    host_port  = cfg.get("gilhari_host_port", 80)

    header("Phase 3 Complete - Summary")
    rows = [
        ("ORM spec (.jdx)",       str(jdx_file.relative_to(root)) + "  (local/JDXDemo use)"),
        ("ORM spec (.docker.jdx)", str((root / CONFIG_DIR / f"{config_name}.config.docker.jdx").relative_to(root)) + "  (packaged in Docker image)"),
        ("gilhari_service.config refs", f"config/{config_name}.config.docker.jdx"),
        ("classnames_map.json",  str(Path(CONFIG_DIR) / "classnames_map.json")),
        ("gilhari_service.config", "gilhari_service.config"),
        ("Dockerfile",         "Dockerfile"),
        ("Docker image",       f"{image_name}:{image_tag}"),
        ("REST base URL",      f"http://localhost:{host_port}/gilhari/v1/<ClassName>"),
        ("Classes",            ", ".join(class_names)),
    ]
    if HAS_RICH:
        tbl = Table(show_header=False, show_lines=True)
        tbl.add_column("Key",   style="cyan")
        tbl.add_column("Value", style="white")
        for k, v in rows:
            tbl.add_row(k, v)
        console.print(tbl)
    else:
        for k, v in rows:
            print(f"  {k:28} {v}")

    docker_built = cfg.get("_docker_built", False)
    print()
    info("Next steps (Phase 4 — manual):")
    step = 1
    if not docker_built:
        print(f"  4{chr(96+step)}. Build the Docker image:")
        print("        build.cmd               (Windows)")
        print("        ./build.sh              (macOS / Linux)")
        step += 1
    print(f"  4{chr(96+step)}. Run run_docker_app.cmd / ./run_docker_app.sh to start the service.")
    step += 1
    print(f"  4{chr(96+step)}. Verify the service is running:")
    print(f"        curl -s http://localhost:{host_port}/gilhari/v1/health/check | python3 -m json.tool")
    step += 1
    print(f"  4{chr(96+step)}. Run the sample curl script to test some REST APIs:")
    print("        sampleCurlCommands.cmd          (Windows)")
    print("        ./sampleCurlCommands.sh         (macOS / Linux)")
    print("        sampleCurlWriteCommands.cmd     (Windows, write ops — all commented out)")
    print("        ./sampleCurlWriteCommands.sh    (macOS / Linux, write ops — all commented out)")
    print("      Responses are logged to curl.log.")
    print()
    info("Phase 5 — Connect an AI agent via ORMCP:")
    print("  See connectORMCP.md in the project directory for tailored")
    print("  installation instructions and Claude Desktop config snippet.")



# ==============================================================================
# JDX KNOWN ERROR PATTERNS
#
# Used by _surface_jdx_error() to match known JDX exception message prefixes
# and surface a plain-English explanation before the raw JDX output.
#
# Scope: errors reachable through orm_skyway's own JDX subprocess calls:
#   - Phase 1 Step 1:  database connection test
#   - Phase 1 Step 10: JDXSchema -reverseEng
#   - Phase 1 Step 12: JDXSchema -metaForceCreate
#
# Runtime Gilhari REST/CRUD errors are out of scope -- they surface in the
# Gilhari container logs, not in orm_skyway subprocess output.
#
# Source: extracted from JDX 05.17 source via FindJDXExceptionCalls.py,
# then triaged and annotated for orm_skyway relevance.
# ==============================================================================

def _surface_jdx_error(output: str, context: str) -> None:
    """Surface a JDX subprocess error with component attribution and, where
    possible, a plain-English explanation derived from known exception patterns.

    Always marks the error as a JDX engine error (not an orm_skyway error) so
    users know which component is responsible and where to look for help.
    The raw JDX output is always printed after the explanation so the user
    has full context. In verbose mode this means the output appears twice —
    once from the caller's verbose_info() and again here — which is acceptable
    since keeping the explanation and output adjacent aids debugging.

    Each entry in _JDX_KNOWN_ERRORS is either a 2-tuple (pattern, explanation)
    or a 3-tuple (pattern, explanation, secondary_pattern). For 3-tuples, both
    the primary and secondary patterns must be present in the output for the
    entry to match — this prevents short/generic primary patterns from firing
    on unrelated output that happens to contain the same short string.
    """
    error(f"[JDX] {context}")
    # Scan known patterns for a plain-English explanation
    matched = False
    if output:
        for entry in _JDX_KNOWN_ERRORS:
            pattern     = entry[0]
            explanation = entry[1]
            secondary   = entry[2] if len(entry) > 2 else None
            if pattern in output and (secondary is None or secondary in output):
                error(f"Likely cause: {explanation}")
                matched = True
                break
    if not matched:
        error(
            "[JDX] This is a JDX ORM engine error — not an orm_skyway error.\n"
            "  If the cause is unclear, check docs/ or contact Software Tree."
        )
    # Always print the raw JDX output adjacent to the explanation.
    if output:
        print("  — JDX detail output follows —")
        print()
        print(output.rstrip())


_JDX_KNOWN_ERRORS = [

    # =========================================================================
    # LICENSE ERRORS
    # Surface before any real work begins.
    # Source: DCD.java
    # =========================================================================

    ("Invalid License Key (",
     "[JDX License] The JDX license key is invalid.\n"
     "  Check the jdx.lic file in your JDX SDK config/ directory.\n"
     "  Contact Software Tree at https://www.softwaretree.com for a valid license."),

    ("Invalid License Key (null)",
     "[JDX License] No JDX license key was found.\n"
     "  Check that jdx.lic exists in your JDX SDK config/ directory and is readable."),

    ("JDX License Manager Exception: JDX tools not licensed",
     "[JDX License] The JDX tools (reverse engineering, schema generation) are not licensed "
     "for this user.\n"
     "  Check the jdx.lic file in your JDX SDK config/ directory."),

    ("JDX License Manager Exception: JDXRuntime not licensed",
     "[JDX License] The JDX runtime is not licensed for this user.\n"
     "  Check the jdx.lic file in your JDX SDK config/ directory."),

    ("JDX License Manager Exception: the evaluation period has exp",
     "[JDX License] The JDX evaluation period has expired.\n"
     "  Contact Software Tree at https://www.softwaretree.com to renew your license."),

    ("JDX License Manager Exception: the subscription period has e",
     "[JDX License] The JDX subscription period has expired.\n"
     "  Contact Software Tree at https://www.softwaretree.com to renew your license."),

    ("JDX License Manager Exception: current JDX tools version not",
     "[JDX License] The current JDX version is not covered by your license.\n"
     "  Contact Software Tree at https://www.softwaretree.com to update your license."),

    ("No license key specified for JDX in the license file",
     "[JDX License] The JDX license file exists but contains no license key.\n"
     "  Check the jdx.lic file in your JDX SDK config/ directory."),

    ("License file name is null or invalid",
     "[JDX License] The JDX license file path is invalid or missing.\n"
     "  Check that jdx.lic exists in your JDX SDK config/ directory."),

    # =========================================================================
    # DATABASE CONNECTION ERRORS
    # Surface during Phase 1 Step 1 (connection test).
    # Source: JNDIDataSource.java, JDXSImpl.java, DCD.java
    # =========================================================================

    ("Exception while trying establishing database connection in J",
     "[Database] Could not establish a database connection.\n"
     "  Check that the database is running and that jdbc_url, db_user,\n"
     "  and db_password in your config file are correct."),

    ("Problem in getting a valid database connection for ORMFile",
     "[Database] Could not get a valid database connection.\n"
     "  Check that the database is running, the JDBC URL is correct, and\n"
     "  the JDBC driver JAR is properly specified in your config file."),

    ("Error: Unknown database type for JDX",
     "[JDX] The database type is not recognized by JDX.\n"
     "  Check the JDX_DBTYPE setting derived from your jdbc_url.\n"
     "  Supported types include: POSTGRES, MYSQL, ORACLE, SQLSERVER, SQLITE,\n"
     "  DB2, SNOWFLAKE, COCKROACHDB, and others.\n"
     "  You can also try setting db_type to GENERIC in your config file."),

    # =========================================================================
    # PHASE 1 REVERSE ENGINEERING ERRORS
    # Surface during Phase 1 Step 10 (JDXSchema -reverseEng).
    # Source: ReferenceKeyInfo.java, ClassInfo.java, ComplexAttribInfo.java,
    #         JDXGen.java, JXUtilities.java, JDXUtil.java
    # =========================================================================

    ("A source attribute of the reference key ",
     "[JDX] A PRIMARY_KEY attribute is missing from the VIRTUAL_ATTRIB declarations "
     "in the .jdx file.\n"
     "  This typically happens when a column type is not supported/recognized during reverse "
     "engineering.\n"
     "  Check the .jdx file: every attribute named in PRIMARY_KEY must also appear\n"
     "  as a VIRTUAL_ATTRIB declaration in the same class block."),

    ("No source attribute specified for the reference key",
     "[JDX] A reference key has no source attributes specified in the .jdx file.\n"
     "  Check the RELATIONSHIP and REFERENCE_KEY specifications in the .jdx file."),

    ("Attribute ",
     "[JDX] An attribute listed in RDBMS_GENERATED was not found in the class.\n"
     "  Check the .jdx file: attribute names in RDBMS_GENERATED must exactly match\n"
     "  a VIRTUAL_ATTRIB declaration in the same class block.",
     "mentioned in the RDBMS_GENERATED"),  # secondary: prevents false matches on "Attribute"

    ("No proper mapping defined for complex attribute ",
     "[JDX] A RELATIONSHIP specification in the .jdx file is missing or incomplete.\n"
     "  Check that every RELATIONSHIP references a valid target class and key.\n"
     "  This can happen if a referenced class was excluded from the table selection."),

    ("Target key not found for constraint ",
     "[JDX] A foreign key relationship could not be mapped to a JDX reference key.\n"
     "  This may indicate a schema introspection issue.\n"
     "  Check the RELATIONSHIP specifications in the .jdx file."),

    ("In setComplex: Class name ",
     "[JDX] A RELATIONSHIP references a class that is not defined in the .jdx file.\n"
     "  Check that all classes referenced in RELATIONSHIP specifications are included.\n"
     "  Re-run Phase 1 with the correct set of tables selected."),

    ("In setComplex: A relationship attribute (",
     "[JDX] A RELATIONSHIP source attribute was not found in the class.\n"
     "  Check the WITH clause of the RELATIONSHIP specification in the .jdx file.\n"
     "  All the attributes specified in the WITH clause should have \n"
     "  VIRTUAL_ATTRIB declaration in the same class block."),

    ("In setComplex: Target reference key ",
     "[JDX] A RELATIONSHIP references a key that does not exist in the target class.\n"
     "  Check the REFERENCES and WITH clauses of the RELATIONSHIP specification."),

    ("In setComplex: source (ForeignKey) attributes must be specif",
     "[JDX] A RELATIONSHIP is missing its source (foreign key) attribute specification.\n"
     "  Check the WITH clause of the RELATIONSHIP specification in the .jdx file."),

    ("No column ",
     "[JDX] A column referenced in the .jdx file does not exist in the database table.\n"
     "  Check that the attribute's COLUMN_NAME (default is the attribute name) or\n"
     "  the name in a SQLMAP specification matches an actual column name,\n"
     "  or re-run reverse engineering to regenerate the .jdx file.",
     " in the table "),  # secondary: prevents false matches on "No column"

    ("Error: Cannot get a default Java type for SQL type",
     "[JDX] An unsupported SQL column type was encountered during reverse engineering.\n"
     "  This column type may not be handled by JDX's default type mapping.\n"
     "  You may need to manually add a VIRTUAL_ATTRIB with an explicit ATTRIB_TYPE\n"
     "  appropriate for this column in the .jdx file during Phase 2."),

    # =========================================================================
    # PHASE 1 METAFORCECREATE ERRORS
    # Surface during Phase 1 Step 12 (JDXSchema -metaForceCreate).
    # Source: DatabaseInfo.java, JDXSetup.java
    # =========================================================================

    ("No metadata found for ",
     "[JDX] The JDXMetadata table does not contain an entry for this ORM ID.\n"
     "  This can happen if -metaForceCreate was skipped or failed on a previous run.\n"
     "  Drop the JDXMetadata and JDXSequence tables and re-run Phase 1."),

    ("Table or view ",
     "[JDX] A table or view referenced in the .jdx file does not exist in the database.\n"
     "  Check that the table name and db_schema in your config match the actual database\n"
     "  schema, and that the JDBC URL points to the correct database.",
     "not found"),  # secondary: prevents false matches on "Table or view"

    ("The class ",
     "[JDX] A class referenced in the .jdx mapping is not configured for JDX OR-Mapping.\n"
     "  This usually means the table (for a class) was not included in the reverse engineering step.\n"
     "  Re-run Phase 1 with the correct set of tables selected.",
     "is not configured for JDX OR-Mapping"),  # secondary: prevents false matches on "The class"

]


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = build_arg_parser()
    args   = parser.parse_args()

    header(f"ORM_Skyway Workflow  v{__version__}")

    # Merge JSON config file; CLI flags take priority
    if args.config_file:
        file_cfg = load_config_file(args.config_file)
        key_map = {
            "jdbc_url":          "jdbc_url",
            "db_user":           "db_user",
            "db_password":       "db_password",
            "db_type":           "db_type",
            "jdbc_driver_class": "jdbc_driver_class",
            "jdbc_driver_jar":   "jdbc_driver_jar",
            "jdbc_driver_lic":   "jdbc_driver_lic",
            "jx_home":           "jx_home",
            "jdx_dev_bin_path":  "jdx_dev_bin_path",
            "object_model_package":  "object_model_package",
            "reverse_eng_template_config": "reverse_eng_template_config",
            "db_schema":         "db_schema",
            "tables":            "tables",
            "skip_reverse_eng":  "skip_reverse_eng",
            "skip_compile":      "skip_compile",
            "db_type":           "db_type",
            "model_overview":    "model_overview",
            "docker_image_name": "docker_image_name",
            "docker_image_tag":  "docker_image_tag",
            "gilhari_host_port": "gilhari_host_port",
            "embed_db_file_in_microservice": "embed_db_file_in_microservice",
            "docker_platform":   "docker_platform",
            "docker_mac_address": "docker_mac_address",
            "docker_hostname":   "docker_hostname",
            "verbose":           "verbose",
        }
        for json_key, arg_dest in key_map.items():
            if json_key in file_cfg and not getattr(args, arg_dest, None):
                setattr(args, arg_dest, file_cfg[json_key])

    # Set verbose mode — CLI --verbose flag or "verbose": true in config file
    global _VERBOSE
    _VERBOSE = bool(getattr(args, "verbose", False))
    global _YES
    _YES     = bool(getattr(args, "yes",     False))

    phase = args.phase   # "1", "3", "1+3", or "introspect"
    info(f"Running phase: {phase}")

    # collect_inputs is always needed (provides package, config_name, paths etc.)
    cfg = collect_inputs(args, phase)

    # B1: Preflight validation — check tools, jars, docker before doing anything
    validate_inputs(cfg, phase)

    # C2: introspect phase — list tables and exit
    if phase == "introspect":
        run_phase_introspect(cfg)
        return

    run_p1 = phase in ("1", "1+3")
    run_p3 = phase in ("3", "1+3")

    config_path     = None
    table_class_map = {}

    if run_p1:
        config_path, table_class_map = run_phase1(cfg, args)

        if phase == "1":
            # Stop here and advise the user on Phase 2
            print()
            header("Phase 1 Complete")
            info("Artifacts written to the project directory.")
            print()
            print("  Phase 2 (manual, optional but recommended) — before running Phase 3:")
            print(f"  1. Refine  config/{cfg['reverse_eng_template_config']}.config.jdx  as needed.")
            print("     (rename attributes, hide columns, adjust types, add transient fields, etc.)")
            print("  2. If you rename or add classes in the .jdx, update the corresponding")
            print("     .java files in src/ and re-run compile.bat / compile.sh.")
            print("  3. Optionally verify with JDXDemo.bat / ./JDXDemo.sh.")
            print()
            print("  When ready for Phase 3, run:")
            _script_path = sys.argv[0]
            print(f"    python3 {_script_path} -f {args.config_file or 'orm_skyway_config.json'} --phase 3")
            return

    if run_p3:
        run_phase3(cfg)

    if run_p1 and run_p3:
        # Full summary only when both phases ran together
        print_summary(cfg, config_path, table_class_map)


if __name__ == "__main__":
    main()
