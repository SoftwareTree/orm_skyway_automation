# Phase 1 — Reverse Engineering

_Last updated: 2026-05-24 13:32 PDT_

**Goal:** Connect to your existing database, select the tables you care about, and automatically generate a JSON object model and (JDX) ORM mapping specification.

Before Phase 1 runs, the script performs a **preflight validation** — checking that `java`, `javac`, the Gilhari SDK jars, and the JDBC driver JAR are all present. If anything is missing you get a clear actionable error before any files are written.

**Run from your project root directory:**
```bat
:: Windows
python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 1

# macOS / Linux
python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 1
```

Or run Phase 1 and Phase 3 together in one go (skipping Phase 2):
```bat
python orm_skyway.py -f orm_skyway_config.json --phase 1+3
```

---

## What Phase 1 does, step by step

### Step 1 — Database connection
The script reads your JDBC URL, credentials, and driver details from the config file, or prompts for them interactively if any are missing. The DB type (MySQL, PostgreSQL, SQLite, etc.) is inferred from the JDBC URL automatically.

### Step 2 — JDX / Gilhari SDK location
The script locates your Gilhari SDK installation via `JX_HOME`. This is needed to invoke the `JDXSchema` reverse-engineering tool.

### Step 3 — Project settings
Collects the Java package name for JSON object classes (optional — leave blank for no package), template config base name, and a one-line object model overview — a short description of your domain that ORMCP reads at startup to give AI agents immediate context about your data.

### Step 4 — Table discovery and selection
The script connects to your database and retrieves all available table and view names. No schema changes are made at this point. An interactive menu then lets you choose which tables to include:

```
Available tables:
   1. customers
   2. order_items
   3. orders
   4. products

Enter table numbers separated by commas/spaces,
ranges like 1-3, 'all' for every table, or table names directly.
Your selection: 1-3, products
```

You are not required to include every table — choose only the ones relevant to your use case.

When running non-interactively (`--yes` mode), set `tables` in the config file or via `--tables`. Use the special value `all` (alone) to select every user table, or a comma-separated list for a specific subset. Run `--phase introspect` first to see all available table names.

### Step 5 — Class name review
For each selected table, the script proposes an object model class name (converting `snake_case` to `PascalCase`, e.g. `order_items` → `OrderItems`). An instance of this (Java) class (also referred as container model class) acts as a container for holding attribute values of a JSON model object. You can accept or rename each object model class name interactively before anything is written to disk.

The class name you choose becomes the REST URL segment in Phase 3 (e.g. `Customer` → `GET /gilhari/v1/Customer`).

### Step 6 — JDXMetadata table
JDX requires a `JDXMetadata` table to track the object model at runtime. If it is absent when Gilhari starts, JDX may attempt to recreate the schema from scratch — destroying your existing data.

The script handles this automatically after compiling the model classes (compilation is required because `JDXSchema` validates the ORM mapping file against the compiled classes on startup):

- **If `JDXMetadata` is already present** in the database — the script skips this step entirely, leaving your existing metadata untouched.
- **If `JDXMetadata` is absent** — the script invokes `JDXSchema -metaForceCreate -IGNORE_WARNINGS`, which creates both the `JDXMetadata` and `JDXSequence` tables in your database. `-metaForceCreate` also drops and recreates `JDXSequence` if a stale copy exists. `-IGNORE_WARNINGS` suppresses harmless warnings when `JDXSequence` does not yet exist.

The `JDX_METADATA_FILE` directive is written into the generated `.config` file automatically (e.g. `jdxMetadata_mysql.jdx` for MySQL, `jdxMetadata_postgres.jdx` for PostgreSQL), and propagates to all derived ORM files (`.revjdx`, `.jdx`, `.docker.jdx`).

### Step 7 — Reverse engineering
The script writes the template config and invokes `JDXSchema -reverseEng`, which reads each table's column metadata and generates:
- `.java` container model classes in `src/<package path>/` (or directly in `src/` if no package is specified)
- `config/<n>.config.revjdx` — the auto-generated ORM mapping specification (immutable; do not edit)
- `config/<n>.config` — the template config, which includes the `JDX_METADATA_FILE` directive pointing to the appropriate per-DB metadata spec file

If `src/` already contains `.java` files from a previous run, the script wipes the entire `src/` directory (and `bin/`) after prompting for confirmation, ensuring no stale files from a previous run — including files from a different package — can be compiled into the new build. If you have hand-edited any `.java` files, save copies before re-running Phase 1.

### Step 8 — Working ORM spec
The auto-generated `.revjdx` is copied to `.jdx` — your working ORM spec, which you can edit freely in Phase 2. The `.revjdx` is kept as an immutable record and should never be edited directly.

### Step 9 — Compile
All generated `.java` container model classes are compiled into `bin/<package path>/` (or directly into `bin/` if no package is specified). The entire `bin/` directory is wiped before compile to ensure no stale `.class` files from any previous run remain.

### Helper scripts
Phase 1 also writes a set of platform-specific helper scripts into the project root:

| Script | Purpose |
|---|---|
| `setEnvironment.bat` / `.sh` | Sets `JX_HOME` and `CLASSPATH` |
| `JDXReverseEngineer.bat` / `.sh` | Runs `JDXSchema -reverseEng` manually if needed |
| `compile.bat` / `.sh` | Recompiles model classes (cleans `bin/<pkg>/` first) |
| `JDXDemo.bat` / `.sh` | Launches the JDXDemo tool for local model verification |

---

## What Phase 1 produces

```
config/
    <n>.config              ← reverse-engineering template
    <n>.config.revjdx       ← auto-generated ORM spec (do not edit)
    <n>.config.jdx          ← working copy (edit this in Phase 2)
    <jdbc-driver>.jar       ← copied here for Docker packaging
src/<package path>/         ← or src/ directly if no package
    Customer.java           ← generated container model classes
    Order.java
    ...
bin/<package path>/         ← or bin/ directly if no package
    Customer.class          ← compiled classes
    Order.class
    ...
setEnvironment.bat / .sh
JDXReverseEngineer.bat / .sh
compile.bat / .sh
JDXDemo.bat / .sh
```

---

## After Phase 1

The script prints a summary of everything created and the exact command to continue with Phase 3. You can proceed immediately, or take time for Phase 2 first.

Phase 2 is **totally optional**. If you run `--phase 1+3`, Phase 2 is skipped entirely and the auto-generated model is used as-is.

→ [Phase 2 — ORM Refinement (optional)](orm_refinement.md)
→ [Phase 3 — Gilhari Packaging](gilhari_microservice_packaging.md)

---

← [Configuration reference](configuration.md) | Next: [Phase 2 — ORM Refinement](orm_refinement.md) →
