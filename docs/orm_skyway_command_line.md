# Command-Line Reference

_Last updated: 2026-08-19 1:44 AM PDT_

← [README](../README.md)

```
python orm_skyway.py [OPTIONS]
```

CLI flags always override values in the config file. Any value not supplied via flag or config file is prompted for interactively.

---

## General options

| Flag | Description |
|---|---|
| `--version` | Print the script version and exit |
| `-f FILE`, `--config-file FILE` | Path to the JSON config file |
| `--project-dir PATH` | Project root directory (default: current working directory). Useful for CI or Makefile invocations where you cannot `cd` first. |
| `--phase {1,3,1+3,introspect}` | Phase(s) to run. Default: `1+3` |
| `--verbose` | Enable detailed output: command lines, file writes, class mappings. Also settable as `"verbose": true` in the config file. |
| `--jdx-debug-level N` (alias: `--jdx_debug_level N`, matching the config-file key spelling) | JDX's own `DEBUG_LEVEL`, written into both the Phase 1 `.jdx` and the Phase 3 `gilhari_service.config`, and passed directly to `JDXSchema` itself as `-DEBUGn` during reverse-engineering. Think of it as **depth, not severity**: a low number means a deep look, right down in the weeds — every SQL statement, every internal warning. A high number gives a high-level, cursory view, with most detail hidden. Default: `5` (the high-level, cursory view). Valid range: `0`–`5` (JDXSchema's own supported range) — an out-of-range value is clamped, with a warning. **`3` specifically is the level to reach for if you just want to see the SQL** — at `3`, JDX/Gilhari logs every SQL statement it executes at runtime, which is the main reason to use this flag when debugging a query/insert/update issue. Going *lower* than `3` adds substantially more internal debugging detail on top of the SQL logging, most of which isn't needed just to see the statements themselves — start at `3` and only go lower if that's not enough. `3` also surfaces a couple of otherwise-silent warnings (e.g. a column excluded from mapping for having a space in its name, or for being a binary type). **Caution:** runtime SQL logging at `<=3` includes literal bound values — avoid this setting in any environment where the log itself might be exposed and the data is sensitive. Also settable as `"jdx_debug_level": N` in the config file. |
| `--yes`, `-y` | Auto-accept all confirmation prompts (non-interactive / CI mode). Requires `--tables` (or `tables` in config) to be set — use `all` to select every table. |

---

## Phase 1 options

| Flag | Description |
|---|---|
| `--jdbc-url URL` | JDBC connection URL |
| `--db-schema SCHEMA` | Database schema/catalog to inspect (blank = default) |
| `--db-user USER` | Database username |
| `--db-password PASSWORD` | Database password |
| `--db-type TYPE` | `POSTGRES` / `MYSQL` / `ORACLE` / `SQLITE` / `MSSQL` / `SNOWFLAKE` / `COCKROACHDB` / `SAPHANA` / `DB2` (auto-detected from URL if omitted). These are the ✅ Verified database types — see the [Supported Databases table](../README.md#supported-databases) in the README. Additional experimental types (`DATABRICKS`, `MARIADB`, `SPANNER`, `YUGABYTE`, and others JDX accepts verbatim) are also supported but not yet fully verified — see [configuration.md](configuration.md) for the full list. `GENERIC` connects to any JDBC-compliant data source not otherwise recognized — see [GENERIC mode](configuration.md#generic-mode--connecting-to-any-jdbc-data-source). |
| `--jdbc-driver-class CLASS` | JDBC driver class name |
| `--jdbc-driver-jar PATH` | Full path to the JDBC driver JAR |
| `--jdbc-driver-lic PATH` | Path to an accompanying JDBC driver license file, if the driver needs one (e.g. CData drivers, used for Excel). Auto-detected by default as a same-stem `.lic` file next to the jar (e.g. `cdata.jdbc.excel.jar` → `cdata.jdbc.excel.lic`) and copied into `config/` for Docker packaging — only set this explicitly if your license file doesn't follow that naming convention. |
| `--jx-home PATH` | Root directory of the Gilhari SDK installation |
| `--object-model-package PKG` | Java package for generated model classes. Omit or leave blank for no package — files go directly into `src/` and `bin/`. |
| `--reverse-eng-template-config NAME` | Base name for the template config file |
| `--model-overview TEXT` | One-line object model description for AI clients |
| `--tables TABLE1,TABLE2,...` | Pre-select tables (skips the interactive selection menu). Use `all` as the sole value to select every user table. **Required when using `--yes`** — the script exits with an error if omitted. Also settable in the config file. |
| `--skip-reverse-eng` | Skip running JDXReverseEngineer |
| `--skip-compile` | Skip Java compilation |

---

## Phase 3 options

| Flag | Description |
|---|---|
| `--docker-image-name NAME` | Docker image name. Must be project-specific to avoid conflicts between projects on the same machine. |
| `--docker-image-tag TAG` | Docker image tag. Default: `1.0` |
| `--gilhari-host-port PORT` | Host port for the Gilhari REST service. Default: `80` |
| `--docker-platform PLATFORM` | Docker target platform, e.g. `linux/amd64` or `linux/arm64`. Default: `linux/amd64` — `softwaretree/gilhari` is currently single-architecture (amd64-only), so this rarely needs to change. On Apple Silicon Macs, the container runs via emulation with a small performance overhead (see the [Apple Silicon note](gilhari_microservice_packaging.md#apple-silicon-platform-note)). Override only if you have a genuinely multi-arch build to target. |
| `--docker-hostname HOSTNAME` | Fixed hostname to assign the container via `docker run --hostname`. Default: the Docker image name. **Required for Excel/CData** — see [configuration.md](configuration.md) for details. Needed for any JDBC driver with node-locked licensing that validates the running container's hostname. |
| `--docker-mac-address MAC` | Fixed MAC address to assign the container via `docker run --mac-address` (e.g. `02:42:ac:11:00:02`). No default — only passed to `docker run` if set. **Required for Excel/CData**, alongside `--docker-hostname` — see [configuration.md](configuration.md) for details, including how to find your machine's real hostname/MAC address (both must match your actual host machine, not arbitrary values, for CData's license check to succeed). |

---

## Phases

| Phase | What it does |
|---|---|
| `1` | Reverse-engineer the DB schema: generates Java model classes, ORM spec, and helper scripts |
| `3` | Package the model into a Gilhari Docker image; generate curl scripts and ORMCP guide |
| `1+3` | Run both phases in sequence (default) |
| `introspect` | Connect to the DB and list all available tables — read-only, no files written |

---

## Common invocations

**Run everything in one command:**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 1+3
```

**Non-interactive run (CI / automation):**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 1+3 --yes
```

**List available tables without writing anything:**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase introspect
```

**Run Phase 1 only, then stop for manual refinement:**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 1
```

**Run Phase 3 only (after manual Phase 2 work):**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 3
```

**Pre-select specific tables to skip the interactive menu:**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 1 --tables employee,department,project
```

**Run from a different directory using --project-dir:**
```bat
python orm_skyway.py -f C:\projects\myservice\orm_skyway_config.json --project-dir C:\projects\myservice --phase 1+3
```

**Override Docker settings from the command line:**
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 3 --docker-image-name my-service --docker-image-tag 2.0
```

**Enable verbose output:**
```bat
python orm_skyway.py -f orm_skyway_config.json --verbose
```

**Print version:**
```bat
python orm_skyway.py --version
```

---

← [README](../README.md) | [Configuration reference](configuration.md) →
