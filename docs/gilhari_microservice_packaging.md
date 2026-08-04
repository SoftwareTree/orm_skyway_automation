# Phase 3 — Gilhari Microservice Packaging

_Last updated: 2026-08-03 5:32 PM PDT_

**Goal:** Package your object model into a self-contained Docker image that exposes a RESTful JSON API for every mapped class.

**Run from your project root directory:**
```bat
:: Windows
python C:\tools\orm_skyway_automation\orm_skyway.py -f orm_skyway_config.json --phase 3

# macOS / Linux
python ~/tools/orm_skyway_automation/orm_skyway.py -f orm_skyway_config.json --phase 3
```

> **Before running Phase 3:** Make sure Docker is running. Start Docker Desktop (Windows/Mac) or the Docker daemon (Linux) if it is not already. You can verify with `docker info`.

> Running the tool itself via [Docker mode](docker_mode.md)? `docker build` for Phase 3 still works — `run_orm_skyway.sh`/`.cmd` mount your host's Docker socket for exactly this purpose.

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
| `config/classnames_map.json` | Maps short REST URL tokens to fully-qualified class names, e.g. `Employee` → `com.example.json.model.Employee` |
| `config/<n>.config.docker.jdx` | The Docker-ready ORM spec with `host.docker.internal` JDBC URL |
| `gilhari/gilhari_service.config` | Gilhari runtime config — points at the `.docker.jdx`, `classnames_map.json`, `bin/`, and `JDBC driver` |
| `gilhari/Dockerfile` | Builds on `FROM softwaretree/gilhari`, adding `bin/`, `config/`, and `gilhari_service.config` |
| `gilhari/build.cmd` / `build.sh` | Runs `docker build -f gilhari/Dockerfile -t <image>:<tag> .` (build context is the project root; `-f` points at the relocated Dockerfile) |
| `gilhari/run_docker_app.cmd` / `.sh` | Runs `docker run -p <host_port>:8081 <image>:<tag>` |

### Builds the Docker image
At the end of Phase 3, the script asks whether to run `docker build` immediately. You can also build later using `gilhari\build.cmd` or `./gilhari/build.sh`.

---

## Why classnames_map.json?

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

## Apple Silicon platform note

The generated Dockerfile and build scripts use `--platform linux/amd64`. On Apple Silicon Macs (M1/M2/M3) this causes a platform mismatch warning during `docker build` and `docker run`. The container still runs correctly via emulation (Rosetta 2), but with a small performance overhead.

A multi-architecture image (`linux/amd64` + `linux/arm64`) would eliminate the warning but requires `docker buildx` and a more complex build pipeline. This is not currently automated by ORM_Skyway. If you need native ARM64 performance, you can manually modify the generated `gilhari/build.sh` to use `docker buildx build --platform linux/amd64,linux/arm64` — but this requires the Gilhari base image to also support ARM64.

The target platform is configurable via `--docker-platform` (or `docker_platform` in the config file), though in practice there's little reason to change it from the `linux/amd64` default today, since `softwaretree/gilhari` is single-architecture.

---

## Fixed hostname / MAC address for the container

`docker run --hostname` is set automatically to the Docker image name by default, so the container's hostname is stable across runs. You can override this with `--docker-hostname` (or `docker_hostname` in the config file). A fixed MAC address can be set via `--docker-mac-address` (or `docker_mac_address`) — there is no default, since Docker's own randomly-assigned MAC is fine for most databases.

**This matters, and is required rather than optional, for JDBC drivers with node-locked licensing** — the confirmed case is CData's Excel driver, whose license check validates the running container's hostname *and* MAC address against your actual host machine's real values, not just any fixed/consistent values. Without both set correctly, Gilhari fails at startup with a "valid license not found" error.

If `orm_skyway.py` detects an Excel connection (`jdbc:excel:` in the URL) with either setting unset, it prints an explicit warning during config collection with the exact commands to find your machine's real hostname and MAC address (`hostname`/`%COMPUTERNAME%` and `getmac /v` on Windows; `hostname` and `ifconfig`/`ip link` on macOS/Linux). See [configuration.md](configuration.md) for the full Excel/CData setup notes.

---

## Docker networking notes

The generated `.docker.jdx` replaces `localhost` with `host.docker.internal` in the JDBC URL so the container can reach the host machine's database. This works out of the box with **Docker Desktop** on Windows and macOS.

**Colima (Apple Silicon) and Linux** do not support `host.docker.internal` by default. If the Gilhari container cannot connect to your database, try one of these approaches:

**Option 1 — Enable `host.docker.internal` in Colima:**
```bash
colima stop
colima start --network-address
```

**Option 2 — Run your database in Docker on a shared network (most portable):**

This works on all platforms — Docker Desktop, Colima, Podman, and Linux — with no host networking dependency.

```bash
# Create a shared Docker network
docker network create gilhari-net

# Run your database on that network (MySQL example)
docker run -d --name mysql-db --network gilhari-net \
  -e MYSQL_ROOT_PASSWORD=secret \
  -e MYSQL_DATABASE=mydb \
  mysql:8

# Run Gilhari on the same network
docker run -d --name my-gilhari-service --network gilhari-net \
  -p 80:8081 my-gilhari-service:1.0
```

Then edit `config/<n>.config.docker.jdx` to use the database container name instead of `host.docker.internal`:
```
JDX_DATABASE JDX:jdbc:mysql://mysql-db:3306/mydb;...
```

Docker's internal DNS resolves container names on the same network automatically.

---

← [Phase 2 — ORM Refinement and Curation](orm_refinement.md) | Next: [Phase 4 — Run and Test](gilhari_testing.md) →
