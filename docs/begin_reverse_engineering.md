# Phase 1 — Reverse Engineering

_Last updated: 2026-10-04 3:30 PM PDT_

**Goal:** Connect to your existing database, select the tables you care about, and automatically generate a JSON object model and (JDX) ORM mapping specification.

Before Phase 1 runs, the script performs a **preflight validation** — checking that `java`, `javac`, the Gilhari SDK jars, and the JDBC driver JAR are all present. If anything is missing you get a clear actionable error before any files are written.

> No local JDK or JDX SDK? See [Docker mode](docker_mode.md) — preflight validation is satisfied automatically inside the image.

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

- **If the database connection is read-only** (the JDBC driver's `Connection.isReadOnly()` returns `true`, e.g. CData's Splunk and Excel drivers) — the script creates neither `JDXTestConnection` nor `JDXMetadata` and prints:
  ```
  The database connection is read-only; skipping creation of the JDXTestConnection and JDXMetadata tables (not needed when the mapping is read from the .jdx file).
  ```
  See [Read-only databases](#read-only-databases) below.

The `JDX_METADATA_FILE` directive is written into the generated `.config` file automatically (e.g. `jdxMetadata_mysql.jdx` for MySQL, `jdxMetadata_postgres.jdx` for PostgreSQL), and propagates to all derived ORM files (`.revjdx`, `.jdx`, `.docker.jdx`).

### Step 7 — Reverse engineering
The script writes the template config and invokes `JDXSchema -reverseEng`, which reads each table's column metadata and generates:
- `.java` container model classes in `src/<package path>/` (or directly in `src/` if no package is specified)
- `config/<n>.config.revjdx` — the auto-generated ORM mapping specification (immutable; do not edit)
- `config/<n>.config` — the template config, which includes the `JDX_METADATA_FILE` directive pointing to the appropriate per-DB metadata spec file

If `src/` already contains `.java` files from a previous run, the script wipes the entire `src/` directory (and `bin/`) after prompting for confirmation, ensuring no stale files from a previous run — including files from a different package — can be compiled into the new build. If you have hand-edited any `.java` files, save copies before re-running Phase 1.

> **Debugging a column that didn't show up as expected?** JDX excludes certain columns during reverse engineering — for example, a binary-typed column (since raw bytes can't be represented in JSON), or one of two columns whose names map to the same attribute name (see [Column names with special characters](#column-names-with-special-characters)). Since JDX 5.28, a column whose name contains a space is no longer excluded; it gets an attribute name with `_` in place of the space. By default (`jdx_debug_level` unset, meaning `5`), the warnings explaining *why* a column was excluded are not visible. Set `--jdx-debug-level 3` (or lower) for this run to see them — see the [command-line reference](orm_skyway_command_line.md) for what else becomes visible at each level, including full runtime SQL statement logging at `<=3`.

### Column names with special characters

Since JDX 5.28, every column has three names:

- its **real name** in the database, exactly as the JDBC driver reports it;
- its **attribute name** in the object model: ASCII letters, digits and `_` are kept, every other character becomes `_` (one for one), case is kept, and a `_` is added in front if the name starts with a digit;
- its **SQL name**: the real name quoted with the driver's identifier quote string (`"..."`, `` `...` `` or `[...]`, from `DatabaseMetaData.getIdentifierQuoteString()`) whenever it differs from the attribute name.

| Column | Attribute |
|---|---|
| `All_Traffic.action` | `All_Traffic_action` |
| `tag::eventtype` | `tag__eventtype` |
| `user-agent` | `user_agent` |
| `price$` | `price_` |
| `display name` | `display_name` |
| `9lives` | `_9lives` |

For each such column, reverse engineering writes a `SQLMAP` line that ties the attribute to the quoted column name, e.g.

```
SQLMAP FOR tag__eventtype COLUMN_NAME "tag::eventtype"
```

so JDX quotes the column in every SQL statement it generates. Keep these lines if you rename the attribute in Phase 2 (change only the attribute name in them).

**Use attribute names in queries.** Filters, `ORDER BY`, projections and aggregates in REST calls (and in ORMCP tool calls) use attribute names, never column names: `filter=All_Traffic_action='allowed'`, not `All_Traffic.action='allowed'`. ORMCP tells AI agents the same.

**Collisions.** If two columns map to the same attribute name, JDX prints a warning such as

```
WARNING!! In the table X, the columns 'x::y' and 'x__y' both map to the attribute name x__y.
```

and maps only one of them; the column whose real name already equals the attribute name (`x__y` here) is ignored. Rename one of the attributes in Phase 2 (with a `SQLMAP` line for its column) if you need both.

If a column name needs quoting but the driver reports no identifier quote string, the column is skipped with a warning.

### Read-only databases

Some data sources can only be read — e.g. Splunk and Excel through CData's JDBC drivers (Excel: `ReadOnly=True` is the driver's default). ORM_Skyway and JDX handle such a source as follows:

- **Phase 1** checks `Connection.isReadOnly()` and, if it is `true`, skips creating the `JDXTestConnection` and `JDXMetadata` tables (see Step 6). Reverse engineering itself only reads metadata, so it works normally.
- **At service start-up**, JDX 5.29 and later log
  ```
  JDX Info: The database connection is read-only; JDX will not create or change any tables (JDXMetadata, JDXSequence, JDXTestConnection or the mapped tables)
  ```
  and read the mapping from the `.jdx` file. If `jdx_force_create_schema` is set, JDX logs `JDX Error: forceCreateSchema is set, but the database connection is read-only; no schema was created.` and creates nothing.
- **Write requests** (POST, PUT, PATCH, DELETE) fail, as the database rejects them. For AI agents, keep ORMCP's `READONLY_MODE` at its default `True`, so the write tools are not offered at all.

> **Known harmless message:** with JDX 5.29, a `CREATE TABLE JDXTestConnection` exception may still appear in the service log at start-up on a read-only source. It does not affect the service; it is due to be removed in JDX 5.30.

The driver decides what `isReadOnly()` returns. If a source cannot be written but its driver reports `false`, Phase 1 tries to create the helper tables and stops with `Could not create JDXTestConnection table.` followed by the database's error. If the driver has a read-only connection property (such as CData's `ReadOnly=True`), set it in `jdbc_url`.

### Step 8 — Working ORM spec
The auto-generated `.revjdx` is copied to `.jdx` — your working ORM spec, which you can edit freely in Phase 2. The `.revjdx` is kept as an immutable record and should never be edited directly.

### Step 9 — Compile
All generated `.java` container model classes are compiled into `bin/<package path>/` (or directly into `bin/` if no package is specified). The entire `bin/` directory is wiped before compile to ensure no stale `.class` files from any previous run remain.

### Helper scripts
Phase 1 also writes a set of platform-specific helper scripts into the `scripts/` subdirectory:

| Script | Purpose |
|---|---|
| `scripts/setEnvironment.bat` / `.sh` | Sets `JX_HOME` and `CLASSPATH` |
| `scripts/JDXReverseEngineer.bat` / `.sh` | Runs `JDXSchema -reverseEng` manually if needed |
| `scripts/compile.bat` / `.sh` | Recompiles model classes (cleans `bin/<pkg>/` first) |
| `scripts/JDXDemo.bat` / `.sh` | Launches the JDXDemo tool for local model verification |

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
scripts/
    setEnvironment.bat / .sh
    JDXReverseEngineer.bat / .sh
    compile.bat / .sh
    JDXDemo.bat / .sh
```

---

## After Phase 1

The script prints a summary of everything created and the exact command to continue with Phase 3. You can proceed immediately, or take time for Phase 2 first.

Phase 2 is **optional** — if you run `--phase 1+3`, it is skipped entirely and the auto-generated model is used as-is. Taking time for Phase 2 is recommended when you want to curate the model for production use.

→ [Phase 2 — ORM Refinement and Curation (optional but recommended)](orm_refinement.md)
→ [Phase 3 — Gilhari Packaging](gilhari_microservice_packaging.md)

---

← [Configuration reference](configuration.md) | Next: [Phase 2 — ORM Refinement and Curation](orm_refinement.md) →
