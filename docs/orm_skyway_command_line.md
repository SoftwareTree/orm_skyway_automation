# Command-Line Reference

_Last updated: 2026-07-14 PDT_

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
| `--yes`, `-y` | Auto-accept all confirmation prompts (non-interactive / CI mode). Requires `--tables` (or `tables` in config) to be set — use `all` to select every table. |

---

## Phase 1 options

| Flag | Description |
|---|---|
| `--jdbc-url URL` | JDBC connection URL |
| `--db-schema SCHEMA` | Database schema/catalog to inspect (blank = default) |
| `--db-user USER` | Database username |
| `--db-password PASSWORD` | Database password |
| `--db-type TYPE` | `MYSQL` / `POSTGRES` / `ORACLE` / `MSSQL` / `SQLITE` / `SNOWFLAKE` / `COCKROACHDB` (auto-detected from URL if omitted). These are the ✅ Verified database types — see the [Supported Databases table](../README.md#supported-databases) in the README. Additional experimental types (`DB2`, `MARIADB`, `DATABRICKS`, `SPANNER`, `YUGABYTE`, and others JDX accepts verbatim) are also supported but not yet fully verified — see [configuration.md](configuration.md) for the full list. |
| `--jdbc-driver-class CLASS` | JDBC driver class name |
| `--jdbc-driver-jar PATH` | Full path to the JDBC driver JAR |
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
