# Phase 3 — Gilhari Microservice Packaging

_Last updated: 2026-05-14 17:48 PDT_

**Goal:** Package your object model into a self-contained Docker image that exposes a RESTful JSON API for every mapped class.

**Run from your project root directory:**
```bat
:: Windows
python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 3

# macOS / Linux
python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 3
```

> **Before running Phase 3:** Make sure Docker is running. Start Docker Desktop (Windows/Mac) or the Docker daemon (Linux) if it is not already. You can verify with `docker info`.

No database connection is needed for Phase 3. It reads only the compiled `.class` files from `bin/` and the current `.jdx` spec from `config/`.

---

## What Phase 3 does

### Creates the Docker ORM spec (.docker.jdx)
Copies `config/<n>.config.jdx` to `config/<n>.config.docker.jdx`, replacing `localhost` and `127.0.0.1` in the JDBC URL with `host.docker.internal`. This is necessary because inside a Docker container, `localhost` refers to the container itself — not your host machine where the database runs. SQLite file-path URLs and remote database hosts are unaffected.

### Discovers compiled classes
Scans `bin/<package path>/` for `.class` files to determine the current set of mapped classes. This reflects whatever was actually compiled after any Phase 2 edits — no database connection is needed.

### Generates Gilhari artifacts

| File | Purpose |
|---|---|
| `config/classnames_map.js` | Maps short REST URL tokens to fully-qualified class names, e.g. `Employee` → `com.example.json.model.Employee` |
| `config/<n>.config.docker.jdx` | The Docker-ready ORM spec with `host.docker.internal` JDBC URL |
| `gilhari_service.config` | Gilhari runtime config — points at the `.docker.jdx`, `classnames_map.js`, `bin/`, and `JDBC driver` |
| `Dockerfile` | Builds on `FROM softwaretree/gilhari`, adding `bin/`, `config/`, and `gilhari_service.config` |
| `build.cmd` / `build.sh` | Runs `docker build -t <image>:<tag> .` |
| `run_docker_app.cmd` / `.sh` | Runs `docker run -p <host_port>:3000 <image>:<tag>` |

### Builds the Docker image
At the end of Phase 3, the script asks whether to run `docker build` immediately. You can also build later using `build.cmd` or `./build.sh`.

---

## Why classnames_map.js?

Without it, REST URLs require the fully-qualified class name:
```
GET /gilhari/v1/com.example.json.model.Employee
```

With it, you use the short class name — the same name as in your `.jdx` spec and your Java source:
```
GET /gilhari/v1/Employee
```

---

## Re-running Phase 3

You can re-run Phase 3 at any time. It is self-contained and does not touch the database or the Phase 1 source files. Common reasons to re-run:

- You refined the `.jdx` in Phase 2 and want to rebuild the image
- You added or removed classes and recompiled
- You changed the Docker image name, tag, or host port

---

## After Phase 3

The script prints a summary of everything created, followed by the next steps for the Phase 4 with ready-to-run `curl` commands for each mapped class.

→ [Phase 4 — Run and Test](gilhari_testing.md)

---

← [Phase 2 — ORM Refinement](orm_refinement.md) | Next: [Phase 4 — Run and Test](gilhari_testing.md) →
