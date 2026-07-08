# Configuration File Reference

_Last updated: 2026-07-08 PDT_

← [README](../README.md)

Save as `orm_skyway_config.json` in your project root directory before running the script. Any value left blank or omitted will be prompted for interactively. CLI flags always override values in this file.

> **Quick start:** Ready-to-use sample configuration files are provided in the `docs/samples/` directory of the repository, one per supported database type. Copy the appropriate file to your project root, rename it to `orm_skyway_config.json`, and edit the values for your environment. See the [Sample configuration files](#sample-configuration-files) section below for the full list.

```json
{
    "jdbc_url":          "jdbc:mysql://localhost:3306/mydb",
    "db_schema":         "",
    "db_user":           "alice",
    "db_password":       "secret",

    "jdbc_driver_jar":   "C:/drivers/mysql-connector-java-8.0.33.jar",
    "jdbc_driver_class": "com.mysql.cj.jdbc.Driver",
    "db_type":           "",

    "jx_home":           "C:/SoftwareTree/JDX5.x",

    "object_model_package":        "com.example.json.model",
    "reverse_eng_template_config": "reverse_eng_template",

    "model_overview": "An e-commerce object model with customers, orders, and products",
    "tables":         "",

    "docker_image_name": "my-ecommerce-service",
    "docker_image_tag":  "1.0",
    "gilhari_host_port": 80,

    "skip_reverse_eng":  false,
    "skip_compile":      false,
    "verbose":           false
}
```

---

## About the `tables` field

The `tables` field controls which database tables are included in the object model:

- **Leave blank** — the script shows an interactive menu listing all available tables; you pick the ones you want.
- **Comma-separated list** — e.g. `"customer,order,product"` — skips the menu and uses exactly those tables.
- **`"all"`** (the word alone) — selects every user table automatically, excluding JDX internal tables.

> **`--yes` mode (non-interactive / CI):** `tables` must be set — either to `"all"` or a specific list. The script exits with an error if `tables` is blank in `--yes` mode. Run `--phase introspect` first to see all available table names.

---

## Field reference

### Database connection (Phase 1)

| Key | Description |
|---|---|
| `jdbc_url` | JDBC connection URL. The DB type (MySQL, PostgreSQL, SQLite, etc.) is inferred automatically from this URL. |
| `db_schema` | Schema or catalog to inspect. The meaning varies by database — see the per-DB examples below. For PostgreSQL, if left blank the script defaults to the `public` schema. |
| `db_type` | Overrides the DB type inferred from `jdbc_url`. Leave blank for auto-detection (recommended). Valid values: `MYSQL`, `POSTGRES`, `ORACLE`, `MSSQL`, `SQLITE`, `DB2` *(experimental)*, `SNOWFLAKE` *(experimental)*, `MARIADB` *(experimental)*, `DATABRICKS` *(experimental)*, `SPANNER` *(experimental)*, `COCKROACHDB` *(experimental)*, `YUGABYTE` *(experimental)*. Useful when the JDBC URL format is non-standard and auto-detection fails. JDX also supports additional tokens (e.g. `ORACLE9`, `GENERIC`) that can be passed through verbatim. |
| `db_user` | Database username |
| `db_password` | Database password |
| `jdbc_driver_jar` | Full path to the JDBC driver JAR. Used both to connect in Phase 1 and copied into `config/` for Docker packaging in Phase 3. |
| `jdbc_driver_class` | JDBC driver class name. A default is suggested based on the detected DB type, but can be overridden — set this explicitly if your JDBC driver JAR uses a different class name. Common values: `com.mysql.cj.jdbc.Driver`, `org.postgresql.Driver`, `org.sqlite.JDBC`, `com.microsoft.sqlserver.jdbc.SQLServerDriver`, `com.ibm.db2.jcc.DB2Driver`, `net.snowflake.client.api.driver.SnowflakeDriver` |

The DB type (MySQL, PostgreSQL, SQLite, etc.) is inferred automatically from the JDBC URL. You only need to supply it manually via `--db-type` if it cannot be detected.

### Per-database `jdbc_url` and `db_schema` examples

The relationship between `jdbc_url` and `db_schema` varies by database. Use the examples below as a guide.

**MySQL**

In MySQL, the database name and schema name are the same concept. The database name appears in the JDBC URL path, and `db_schema` should match it to scope table discovery to that database only.

If `db_schema` is left blank, the script extracts the database name from the JDBC URL automatically (e.g. `sakila` from `jdbc:mysql://localhost:3306/sakila`) and uses it as the effective schema. This avoids cross-database table leakage. If extraction fails, a warning is shown and all databases are scanned.

```json
"jdbc_url":   "jdbc:mysql://localhost:3306/sakila",
"db_schema":  "sakila"
```

`db_schema` can also be left blank — the script will extract `sakila` from the URL:

```json
"jdbc_url":   "jdbc:mysql://localhost:3306/sakila?useSSL=FALSE",
"db_schema":  ""
```

If your MySQL URL includes connection parameters (e.g. `?useSSL=FALSE`), include them in `jdbc_url` — `db_schema` still just holds the database name if set explicitly.

If `db_schema` is set explicitly, it must match the database name in `jdbc_url` — in MySQL these are the same concept and a mismatch will cause the script to exit with an error.

**PostgreSQL**

In PostgreSQL, the database name and schema name are separate concepts. The database name goes in the JDBC URL path; the schema name (e.g. `public`, `myschema`) goes in `db_schema`. The script automatically injects `?currentSchema=<db_schema>` into the JDBC URL written into the generated ORM files so the JDX runtime resolves tables in the correct schema.

If `db_schema` is left blank, the script defaults to the `public` schema — this avoids ambiguity when JDXMetadata tables exist in multiple schemas and keeps the object model focused on one domain. If your tables are in a different schema, set `db_schema` explicitly.

```json
"jdbc_url":   "jdbc:postgresql://localhost:5432/mydb",
"db_schema":  "public"
```

To target a non-default schema:

```json
"jdbc_url":   "jdbc:postgresql://localhost:5432/mydb",
"db_schema":  "myschema"
```

If you already include `?currentSchema=myschema` in your JDBC URL, leave `db_schema` blank — the script extracts it from the URL automatically. If both are set, they must match or the script will exit with an error.

```json
"jdbc_url":   "jdbc:postgresql://localhost:5432/mydb?currentSchema=myschema",
"db_schema":  ""
```

**Oracle**

In Oracle, `db_schema` is the schema owner (typically the username). Leave it blank to inspect all schemas visible to the connecting user, or set it to the specific owner whose tables you want.

```json
"jdbc_url":   "jdbc:oracle:thin:@localhost:1521:orcl",
"db_schema":  "MYOWNER"
```

**SQLite**

SQLite has no schema concept. Leave `db_schema` blank and put the file path in `jdbc_url`. No credentials are needed.

```json
"jdbc_url":   "jdbc:sqlite:./config/my_database.db",
"db_schema":  ""
```

> **Important — local use:** The JDBC URL path is resolved relative to the working directory of the process connecting to the database. Always run the script from your project root directory. If the file is not found, SQLite silently creates a new empty database, which will appear to connect successfully but contain no tables.

**SQLite and Docker (Phase 3):**

SQLite is file-based, not network-based. Unlike other databases where `localhost` is replaced with `host.docker.internal`, the database file itself must be accessible inside the container. ORM_Skyway handles this automatically in two modes controlled by `embed_db_file_in_microservice`:

- **Mount mode** (`embed_db_file_in_microservice: false`, default) — the database directory is mounted into the container at runtime via a Docker volume. The generated `run_docker_app` scripts include the `-v` mount automatically. This is recommended for development since DB changes are visible immediately without rebuilding the image. SQLite WAL files (`db-wal`, `db-shm`) and other companion files are accessible because the entire directory is mounted, not just the single file.

- **Embed mode** (`embed_db_file_in_microservice: true`) — the database directory is baked into the Docker image at build time. The image is fully self-contained and shippable without any host filesystem dependency. Use this for demos, certification, or distribution. Note: data is static — rebuild the image to pick up any changes to the database file.

In both modes, the script rewrites the JDBC URL in `.docker.jdx` to a fixed container path (`/opt/<image_name>/db/<filename>`) regardless of whether the original path was relative or absolute, ensuring consistent behaviour across all operating systems.

**Microsoft SQL Server**

In MSSQL, the database name appears in the URL and `db_schema` holds the schema (typically `dbo`).

```json
"jdbc_url":   "jdbc:sqlserver://localhost:1433;databaseName=mydb",
"db_schema":  "dbo"
```

**IBM DB2** *(experimental — not yet verified)*

In DB2, `db_schema` is the schema name (typically the username or a named schema). The database name goes in the JDBC URL.

```json
"jdbc_url":   "jdbc:db2://localhost:50000/mydb",
"db_schema":  "MYSCHEMA",
"jdbc_driver_class": "com.ibm.db2.jcc.DB2Driver"
```

See [IBM DB2 JDBC driver documentation](https://www.ibm.com/docs/en/db2-big-sql/7.1.0?topic=drivers-jdbc-driver) for driver download and setup instructions.

**Snowflake** *(experimental)*

> **Note:** Snowflake support is experimental and has not yet been fully verified end-to-end. Use with caution and test thoroughly before using in production.

In Snowflake, the database, schema, and warehouse are all specified as URL parameters. The `db_schema` field holds the schema name. If left blank, the script extracts the schema from the `schema=` URL parameter automatically. If both are set, they must match or the script will exit with an error.

```json
"jdbc_url":   "jdbc:snowflake://<account>.snowflakecomputing.com/?db=<database>&schema=<schema>&warehouse=<warehouse>",
"db_schema":  "<schema>",
"jdbc_driver_class": "net.snowflake.client.api.driver.SnowflakeDriver"
```

`db_schema` can also be left blank — the script will extract the schema from the URL `schema=` parameter automatically:

```json
"jdbc_url":   "jdbc:snowflake://myaccount.snowflakecomputing.com/?db=mydb&schema=myschema&warehouse=mywarehouse",
"db_schema":  ""
```

See [Snowflake JDBC driver documentation](https://docs.snowflake.com/en/developer-guide/jdbc/jdbc) for driver download and setup instructions.

**MariaDB** *(experimental — not yet verified)*

MariaDB is MySQL-compatible. The `db_schema` field behaves the same as MySQL — it should match the database name in the JDBC URL, or leave blank for auto-extraction.

```json
"jdbc_url":   "jdbc:mariadb://localhost:3306/mydb",
"db_schema":  "mydb",
"jdbc_driver_class": "org.mariadb.jdbc.Driver"
```

**Databricks** *(experimental — not yet verified)*

Databricks uses token-based authentication. The `db_user` should be set to `token` and `db_password` to your personal access token.

```json
"jdbc_url":   "jdbc:databricks://<host>:443/default;transportMode=http;ssl=1;httpPath=<http_path>;AuthMech=3",
"db_schema":  "<schema>",
"db_user":    "token",
"db_password":"<your_token>",
"jdbc_driver_class": "com.databricks.client.jdbc.Driver"
```

**Google Spanner** *(experimental — not yet verified)*

Uses Spanner's PostgreSQL-compatible interface. Two connection options are available — Option B is recommended since it uses the same PostgreSQL JDBC driver as all other PostgreSQL-family databases in `orm_skyway`, and is fully compatible with `orm_skyway`'s UUID support.

**Option B (Recommended): PGAdapter + standard PostgreSQL JDBC driver**

The easiest way to run locally on Windows is the combined PGAdapter + Spanner emulator Docker image — no Google Cloud credentials, no project, no `gcloud` CLI, and no separate JRE required:

```bat
docker pull gcr.io/cloud-spanner-pg-adapter/pgadapter-emulator
docker run -d -p 5432:5432 -p 9010:9010 -p 9020:9020 gcr.io/cloud-spanner-pg-adapter/pgadapter-emulator
```

This starts both PGAdapter and the Spanner emulator in one container. Any database name you connect to is auto-created — no `CREATE DATABASE` step needed. Data is stored in memory only — all state is lost when the container stops.

Connect using the standard PostgreSQL JDBC driver on `localhost:5432` (pgjdbc 42.0.0 or higher — the `postgresql-42.2.29.jar` already bundled in the Gilhari SDK works):

```json
"jdbc_url":          "jdbc:postgresql://localhost:5432/test-db",
"db_schema":         "",
"db_user":           "",
"db_password":       "",
"jdbc_driver_jar":   "C:/SoftwareTree/JDX5.x/external_libs/postgresql-42.2.29.jar",
"jdbc_driver_class": "org.postgresql.Driver"
```

**Spanner-specific schema notes** — Spanner's PostgreSQL dialect has a few differences from standard PostgreSQL worth knowing before designing a test schema:
- Every table must have an explicit `PRIMARY KEY` — no implicit rowid
- `SERIAL` is not supported — use `BIGINT` or `VARCHAR` PKs, or UUID with `gen_random_uuid()` (supported in Spanner's PostgreSQL dialect)
- Foreign key constraints are not enforced by the local emulator (they work on real Cloud Spanner)
- Some DDL features differ — check [Spanner PostgreSQL dialect DDL](https://cloud.google.com/spanner/docs/reference/postgresql/data-definition-language) if you hit issues

For Cloud Spanner (not emulator), PGAdapter connects to your real instance and requires Google Cloud credentials. See [Start PGAdapter](https://cloud.google.com/spanner/docs/pgadapter-start) for details.

**Option A (Fallback): Spanner JDBC driver directly**

If PGAdapter isn't an option, use the Spanner JDBC driver to connect directly. Download it from [https://cloud.google.com/spanner/docs/jdbc-drivers](https://cloud.google.com/spanner/docs/jdbc-drivers).

For the local emulator:
```json
"jdbc_url":          "jdbc:cloudspanner://localhost:9010/projects/emulator-project/instances/test-instance/databases/test-db;usePlainText=true",
"db_schema":         "",
"db_user":           "",
"db_password":       "",
"jdbc_driver_jar":   "C:/drivers/google-cloud-spanner-jdbc-x.x.x.jar",
"jdbc_driver_class": "com.google.cloud.spanner.jdbc.JdbcDriver"
```

For Cloud Spanner, replace the URL with:
```json
"jdbc_url": "jdbc:cloudspanner:/projects/<project>/instances/<instance>/databases/<database>?dialect=POSTGRESQL"
```

See `docs/sample/orm_skyway_config_spanner.json` for a complete sample configuration with both options.

**Other file-based databases (H2, HSQLDB, Derby, Excel)**

ORM_Skyway includes implicit support for other file-based databases. The same Docker volume mount / embed logic that applies to SQLite also applies to H2 (file mode), HSQLDB (file mode), Derby (embedded mode), and Excel (via JDBC). Sample configuration files for these databases are provided in `docs/samples/`. Note that JDX support for these has not been fully verified end-to-end and may require further enhancements.

**CockroachDB and YugabyteDB** *(experimental — not yet verified)*

Both are PostgreSQL-compatible. Use the standard PostgreSQL JDBC driver and follow the same `db_schema` guidance as PostgreSQL.

```json
"jdbc_url":   "jdbc:postgresql://<host>:<port>/<database>",
"db_schema":  "public",
"jdbc_driver_class": "org.postgresql.Driver"
```

### SDK location (Phase 1)

| Key | Description |
|---|---|
| `jx_home` | Root directory of the Gilhari SDK installation (the directory containing `libs/`, `external_libs/`, and `config/`). Can also be set as the `JX_HOME` environment variable. |

### Project settings (Phase 1)

| Key | Description |
|---|---|
| `object_model_package` | Java package for the generated model classes, e.g. `com.example.json.model`. Leave blank for no package — `.java` files are generated directly into `src/` and `.class` files into `bin/`, with no `package` declaration. |
| `reverse_eng_template_config` | Base name for the generated config files. Produces `config/<n>.config`, `config/<n>.config.revjdx`, `config/<n>.config.jdx`, and `config/<n>.config.docker.jdx`. |
| `model_overview` | A one-line description of your object model. Written into the ORM spec and read by ORMCP at startup to give AI agents domain context. Example: `"An e-commerce object model with customers, orders, and products"` |
| `tables` | Pre-selects tables to expose, skipping the interactive selection menu. Comma-separated list of table names (e.g. `"customer,order,product"`), or the special value `"all"` (alone) to select every user table. **Required in `--yes` mode** — the script exits with an error if blank. Leave blank to select interactively. Run `--phase introspect` first to see all available table names. |

The generated `config/<n>.config` file also includes a `JDX_METADATA_FILE` directive (e.g. `jdxMetadata_mysql.jdx` for MySQL, `jdxMetadata_postgres.jdx` for PostgreSQL) which tells JDX where to find its internal metadata table definitions. This is written automatically based on the detected DB type and propagates to all derived ORM files (`.revjdx`, `.jdx`, `.docker.jdx`). You do not need to set this manually.

### Docker / Gilhari settings (Phase 3)

| Key | Description |
|---|---|
| `docker_image_name` | Name for the Docker image. Also used as `gilhari_microservice_name` in `gilhari_service.config`. **Required** — must be set to a project-specific name (e.g. `my-sakila-service`) to avoid Docker image conflicts between projects on the same machine. The script will prompt if left blank. |
| `docker_image_tag` | Docker image tag. Default: `1.0` |
| `gilhari_host_port` | Host port mapped to Gilhari's internal port. Default: `80`. The service will be reachable at `http://localhost:<port>/gilhari/v1/`. |
| `embed_db_file_in_microservice` | Only applies to file-based databases (SQLite, H2 file mode, HSQLDB file mode, Derby embedded, Excel). Set `true` to bake the database directory into the Docker image (self-contained/shippable). Default `false` = mount the host database directory at runtime via Docker volume — recommended for development. See the SQLite section above for full details. |

### Script behaviour

| Key | Description |
|---|---|
| `skip_reverse_eng` | Set `true` to skip running JDXReverseEngineer (useful to recompile or re-run Phase 3 without repeating the schema step). Default: `false` |
| `skip_compile` | Set `true` to skip Java compilation. Default: `false` |
| `verbose` | Set `true` to enable detailed output: command lines, file writes, class mappings. Equivalent to `--verbose`. Default: `false` |

---

## Sample configuration files

Ready-to-use sample configuration files are provided in the `docs/samples/` directory of the repository, one per supported database type. Copy the appropriate file to your project root, rename it to `orm_skyway_config.json`, and edit the values for your environment.

| File | Database |
|---|---|
| `orm_skyway_config_mysql.json` | MySQL |
| `orm_skyway_config_postgres.json` | PostgreSQL |
| `orm_skyway_config_oracle.json` | Oracle |
| `orm_skyway_config_sqlserver.json` | Microsoft SQL Server |
| `orm_skyway_config_sqlite.json` | SQLite |
| `orm_skyway_config_db2.json` | IBM DB2 *(experimental)* |
| `orm_skyway_config_snowflake.json` | Snowflake *(experimental)* |
| `orm_skyway_config_mariadb.json` | MariaDB *(experimental)* |
| `orm_skyway_config_databricks.json` | Databricks *(experimental)* |
| `orm_skyway_config_spanner.json` | Google Cloud Spanner *(experimental)* |

Each file includes comments explaining the key settings for that database type.

---

## Notes

- **CLI flags always override config file values.** Run `python jdx_reverse_engineer.py --help` or see the [command-line reference](orm_skyway_command_line.md) for all available flags.
- **Sensitive values** like `db_password` can be left blank and entered interactively at runtime rather than stored in the file.
- **Do not commit real credentials** to version control. The template in the repo has no real values and is safe to commit.

---

← [README](../README.md) | Next: [Phase 1 — Reverse Engineering](begin_reverse_engineering.md) →
