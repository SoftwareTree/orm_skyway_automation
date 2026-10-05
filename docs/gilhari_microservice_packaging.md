# Phase 3 — Gilhari Microservice Packaging

_Last updated: 2026-10-04 3:30 PM PDT_

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

With `credentials_via_env` on, the database user name and password in the `.docker.jdx` are replaced with placeholders (and `User=` / `Password=` are removed from the JDBC URL), so they never reach the image — see [Credentials](#credentials-credentials_via_env) below.

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
| `gilhari/run_docker_app.cmd` / `.sh` | Starts the container (`docker run -d --name <image> -p <host_port>:8081 <image>:<tag>`, plus the hostname, MAC address, network and credential options described below) and waits until `/health/check` answers — see [The run_docker_app launcher](#the-run_docker_app-launcher) |
| `gilhari/orm_skyway.env` | Only with `credentials_via_env`: the database user name and password for `docker run --env-file`. Created empty once; never overwritten; git-ignored |
| `gilhari/sampleCurlCommands.cmd` / `.sh`, `sampleCurlWriteCommands.cmd` / `.sh` | Sample REST calls for every mapped class (Phase 4) |
| `gilhari/connectORMCP.md` | ORMCP connection guide with this project's values filled in (Phase 5) |
| `.dockerignore` (project root) | Keeps files with credentials (and, in mount mode, the database file) out of the Docker build context — see [.dockerignore](#dockerignore) |

### Builds the Docker image
At the end of Phase 3, the script asks whether to run `docker build` immediately. You can also build later using `gilhari\build.cmd` or `./gilhari/build.sh`.

---

## The run_docker_app launcher

`gilhari/run_docker_app.cmd` / `.sh`:

1. returns at once if a service already answers `/health/check` on the host port;
2. with `credentials_via_env`, warns if `JDX_DB_USER` or `JDX_DB_PASSWORD` is set neither in `gilhari/orm_skyway.env` nor in the shell;
3. removes any old container with the same name;
4. creates the service's Docker network if one is used and does not exist yet (see [Docker network](#docker-network-for-the-service-container));
5. starts the container in the background;
6. waits up to 3 minutes for `/health/check` (cloud databases can take a while). If the container stops in the meantime (e.g. it cannot log in to the database), it says so and prints the last 20 lines of `docker logs` instead of waiting.

---

## Credentials (`credentials_via_env`)

By default the database user name and password are written into `config/<n>.config.docker.jdx`, which is copied into the image. Set `"credentials_via_env": true` in the config file to supply them when the container starts instead:

```
# gilhari/orm_skyway.env  (created by Phase 3; fill in; do not commit)
JDX_DB_USER=alice
JDX_DB_PASSWORD=secret
```

`run_docker_app` passes `--env-file gilhari/orm_skyway.env -e JDX_DB_USER -e JDX_DB_PASSWORD`, so values set in the shell before running it take precedence over the file. Full details, including the precedence rules: [configuration.md](configuration.md#keeping-credentials-out-of-the-docker-image-credentials_via_env).

Do not add `db_username` / `db_password` to `gilhari/gilhari_service.config`: that file is copied into the image too (Phase 3 writes a `_comment_credentials` note into it saying so).

---

## .dockerignore

Phase 3 writes a marked block into `.dockerignore` in the project root (Docker reads it from the build context, which is the project root, not from `gilhari/`). The block is regenerated on every run; lines you add above or below it are kept, in place.

The block excludes the files that carry database credentials but are not needed by the service: `config/*.config`, `config/*.config.jdx`, `config/*.config.revjdx`, `config/*.config.bak`, `gilhari/orm_skyway.env` and `orm_skyway_config.json`. The service's own spec, `config/*.config.docker.jdx`, is not matched by these patterns. For a file-based database in mount mode, the database file and its companion files are excluded as well (they are mounted at run time).

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

**This is required for JDBC drivers with node-locked licences** — CData's drivers (Excel, Splunk, ...), whose licence check uses the container's host name *and* MAC address. Both must match the values in effect when the licence was activated (usually your host machine's own values). Without them, the service starts and even reports healthy, but every data request fails with a licence error.

If `orm_skyway.py` detects a CData driver (`jdbc:excel:` or `jdbc:splunk:` URL, or a `cdata` driver class) with either setting unset, it prints a warning with the commands to find the values (`hostname` and `getmac /v` on Windows; `hostname` and `ifconfig` / `ip link` on macOS/Linux). See [configuration.md](configuration.md#node-locked-jdbc-drivers-cdata-hostname-mac-address-and-docker-network) for the full notes.

---

## Docker network for the service container

When `docker_mac_address` is set, each service runs on its own Docker network, `<docker_image_name>-net`, which `run_docker_app` creates if it does not exist. Phase 3 prints `Service container network: <name>`. The reason: services built for the same node-locked licence share a MAC address, and two containers with the same MAC address on one Docker network lose connections intermittently (about 15–20% of requests in testing, health checks included).

Override it with `docker_network` (config file) or `--docker-network`:

- **a network name** — the container joins that network (created if missing). Use it to share a network deliberately, e.g. with your database container (Option 2 below) or an ORMCP container. Never put two containers with the same MAC address on one network.
- **`bridge`** (or `default`) — Docker's default bridge, even with a MAC address set.

Without a MAC address, no network is set unless you set `docker_network`. Port publishing (`-p`) and `host.docker.internal` work the same on a user-defined network.

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

With ORM_Skyway, the simplest way to do the last step is `"docker_network": "gilhari-net"` in the config file: the generated `run_docker_app` then starts the service on that network.

Then edit `config/<n>.config.docker.jdx` to use the database container name instead of `host.docker.internal`:
```
JDX_DATABASE JDX:jdbc:mysql://mysql-db:3306/mydb;...
```

Docker's internal DNS resolves container names on the same network automatically.

---

← [Phase 2 — ORM Refinement and Curation](orm_refinement.md) | Next: [Phase 4 — Run and Test](gilhari_testing.md) →
