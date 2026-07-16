Copyright (c) 2025 SoftwareTree, Inc. All Rights Reserved.
# Make Your Database AI-Ready — Automatically

**Your business data is already in databases. The missing piece is making it accessible to AI.**

**ORM_Skyway** automation tool connects your existing relational databases to AI agents — automatically. Point it at your database, and within minutes you have a secure, governed API layer that lets AI reason about your business objects: customers, orders, products, employees — whatever your domain holds.

Immediately start leveraging your data for AI applications through a secure and efficient ORM pipeline.

No new database. No data migration. No custom API development. And because you control exactly what the AI can see, sensitive data stays protected.

**Turn your existing database into an AI-ready asset — in minutes, not months.**

---

> **For developers:** Your relational database. AI-ready in one command.
>
> ORM_Skyway reverse-engineers any existing relational database into a curated JSON object model (using JDX), packages it as a RESTful microservice (using Gilhari), and connects it to AI agents via MCP (using ORMCP) — automatically. Instead of raw SQL or generic REST, AI agents get a curated, object-oriented view of your domain data. Shaped JSON objects keep token usage low. Sensitive columns removed from the ORM spec stay invisible to the agent. The `.jdx` mapping file is your governance boundary.
>
> MySQL, PostgreSQL, Oracle, SQLite, DB2, SQL Server, ... — one tool, one command, zero hand-written API code.

---

## What it does

ORM_Skyway (`orm_skyway.py`) automates the journey from a relational database to a live REST microservice (Gilhari), and from there to an AI agent that can query your data through natural language.

```
Your Database  ──►  Object Model  ──►  REST Microservice  ──►  AI Agent
                   (auto-generated)     (Docker image)        (via ORMCP)
```

**The AI agent gets a curated, object-oriented view of your data — not raw tables or SQL. This improves reasoning clarity, keeps token usage low, and gives you a clean governance boundary: the agent sees only what your domain model exposes.**

### The ORM_Skyway Pipeline

ORM_Skyway creates and connects three elevated ORM pipelines — like a skyway connecting buildings above ground level:

```
ORMCP Pipeline   ─────────────────────────────────  ← AI / MCP layer
                              ↑
Gilhari Pipeline ─────────────────────────────────  ← REST microservice layer
                              ↑
JDX Pipeline     ─────────────────────────────────  ← Java/JSON ORM layer
                              ↑
Your Database    ═════════════════════════════════  ← foundation
```

Each layer builds on the one below. ORM_Skyway automates the entire stack — from raw database schema to AI-ready API — in one elevated, protected pathway.

---

## The workflow at a glance

| Phase | What happens | How |
|---|---|---|
| **1 — Reverse engineer** | Reads your DB schema, generates Java/JSON model classes and ORM spec | Script (automated) |
| **2 — Refine & Curate** | Rename attributes, hide sensitive columns, curate the model; verify mapping with JDXDemo GUI tool | Manual — optional but recommended (edit one text file) |
| **3 — Package** | Builds a Gilhari microservice Docker image with REST APIs for every mapped class | Script (automated) |
| **4 — Run & test** | Start the container; verify with curl or Postman | Manual — optional but recommended |
| **5 — Connect AI** | Point ORMCP at the running Gilhari microservice; add one config snippet to your AI client | Minutes |

---

## Prerequisites

- Python 3.8+
- JDK 8+ on your PATH
- Gilhari SDK (includes JDX ORM libraries): [Introduction](https://softwaretree.com/v1/products/gilhari/gilhari_introduction.php) | [Download](https://www.softwaretree.com/v1/products/gilhari/download-gilhari.php)
- ORMCP (for Phase 5): [Introduction](https://www.softwaretree.com/v1/products/ormcp/ormcp-introduction.php) | [Download](https://www.softwaretree.com/v1/products/ormcp/download.php)
- JDBC driver JAR for your database
- Docker (for Phases 3–4)
- `pip install rich` *(optional — nicer terminal output)*

> [!TIP]
> Don't want to install a local JDK/JDX SDK? [Docker mode](docs/docker_mode.md) runs the whole tool — Phases 1 and 3 — with only Docker installed.

---

## Quick start

### Windows

```bat
:: 1. Clone the repo to a convenient tools location — do this once, not per project
cd C:\tools
git clone https://github.com/SoftwareTree/orm_skyway_automation.git

:: 2. Create a project directory anywhere you like and enter it
mkdir C:\projects\my_service
cd C:\projects\my_service

:: 3. Copy the template config into your project directory and edit it
copy C:\tools\orm_skyway_automation\orm_skyway_config.json .
notepad orm_skyway_config.json

:: 4. Run Phase 1 (reverse-engineer) + Phase 3 (build Gilhari Docker image) together
python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 1+3

:: 5. Start the Gilhari microservice
run_docker_app.cmd

:: 6. Verify
curl -s http://localhost:80/gilhari/v1/health/check | python -m json.tool
```

### macOS / Linux

```bash
# 1. Clone the repo to a convenient tools location — do this once, not per project
cd ~/tools
git clone https://github.com/SoftwareTree/orm_skyway_automation.git

# 2. Create a project directory anywhere you like and enter it
mkdir ~/projects/my_service
cd ~/projects/my_service

# 3. Copy the template config into your project directory and edit it
cp ~/tools/orm_skyway_automation/orm_skyway_config.json .
nano orm_skyway_config.json   # or your preferred editor

# 4. Run Phase 1 (reverse-engineer) + Phase 3 (build Gilhari Docker image) together
python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 1+3

# 5. Start the Gilhari microservice
./run_docker_app.sh

# 6. Verify
curl -s http://localhost:80/gilhari/v1/health/check | python -m json.tool
```

The tool repo (`orm_skyway_automation/`) and your service project directories are completely independent. You can have as many service projects as you like in different locations — each one just references the same cloned tool.

Want to pause between phases to refine the ORM spec first?

**Windows:**
```bat
python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 1

:: (optionally edit config\*.jdx, then recompile with compile.bat)

python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 3
```

**macOS / Linux:**
```bash
python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 1

# (optionally edit config/*.jdx, then recompile with ./compile.sh)

python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 3
```

---

## Connecting an AI agent (ORMCP)

Once your Gilhari microservice is running, connecting it to an AI agent takes just a few minutes.

[ORMCP](https://github.com/SoftwareTree/ormcp-docs) is an MCP server that bridges AI language models to your Gilhari microservice. The agent reasons about your domain objects — `Employee`, `Order`, `Product` — not raw table rows.

```bat
pip install ormcp-server
```

Then add one entry to your AI client config. For **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "my-ormcp-server": {
      "command": "ormcp-server",
      "args": [],
      "env": {
        "GILHARI_BASE_URL": "http://localhost:80/gilhari/v1/",
        "MCP_SERVER_NAME": "MyORMCPServer"
      }
    }
  }
}
```

Claude Desktop starts the ORMCP server automatically — no separate terminal needed. You can then ask things like *"Show me all orders placed this month"* and it queries your database through your curated domain model.

> **Beta:** ORMCP is currently in beta — free to use for testing and evaluation, not yet for production. No account or access request is needed to install it; `pip install ormcp-server` works directly. See [softwaretree.com/products/ormcp](https://www.softwaretree.com/v1/products/ormcp/ormcp-introduction.php) for details.

---

## Supported Databases

| Database | Status |
|---|---|
| PostgreSQL | ✅ Verified |
| MySQL | ✅ Verified |
| Oracle | ✅ Verified |
| SQLite | ✅ Verified |
| SQL Server (MSSQL) | ✅ Verified |
| DB2 | ⚠️ Experimental |
| Snowflake | ✅ Verified |
| Databricks | ⚠️ Experimental |
| SAP HANA | ⚠️ Experimental |
| MariaDB | ⚠️ Experimental |
| Spanner (PostgreSQL interface) | ⚠️ Experimental |
| CockroachDB (PostgreSQL interface) | ✅ Verified |
| YugabyteDB | ⚠️ Experimental |

---

## Want to go deeper?

- [Docker mode — run with only Docker installed](docs/docker_mode.md)
- [Configuration file reference](docs/configuration.md)
- [Phase 1 — Reverse engineering in detail](docs/begin_reverse_engineering.md)
- [Phase 2 — ORM refinement and curation guide](docs/orm_refinement.md)
- [Phase 3 — Gilhari packaging in detail](docs/gilhari_microservice_packaging.md)
- [Phase 4 — Testing with curl and Postman](docs/gilhari_testing.md)
- [Phase 5 — ORMCP / AI integration](docs/ai_ormcp_gilhari_integration.md)
- [Command-line reference](docs/orm_skyway_command_line.md)
- [Project layout](docs/project_layout.md)
- [ORMCP documentation](https://github.com/SoftwareTree/ormcp-docs)
- [Gilhari SDK](https://softwaretree.com/v1/products/gilhari/gilhari_introduction.php)

---

*ORM_Skyway is built on [Software Tree's JDX ORM, Gilhari, and ORMCP](https://softwaretree.com)*
