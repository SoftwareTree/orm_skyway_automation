# Docker Mode — Run with Zero Local Prerequisites

_Last updated: 2026-06-26 PDT_

← [README](../README.md)

**Goal:** Run the entire Phase 1 + Phase 3 workflow with only Docker installed — no local JDK, no local JDX SDK, no local Python required.

This is an alternative to the standard way of running `orm_skyway.py` described throughout the rest of these docs — not a replacement for it. If you already have a working local install (JDK + JDX SDK + Python), the standard approach in the [Quick start](../README.md#quick-start) section still works exactly as documented, with no changes. Pick whichever fits your situation; both produce the same results.

---

## Why

Normally, running `orm_skyway.py` requires:
- Python 3.8+
- A JDK on your `PATH`
- The Gilhari SDK (JDX libraries)
- The right JDBC driver JAR for your database

Docker mode replaces the first three with one: **Docker**. The `softwaretree/orm_skyway` image bundles Python and the JDX SDK, plus JDBC drivers for three common databases (MySQL, PostgreSQL, SQLite) — though those bundled versions may not always be the latest, and for any other database you'll still set `jdbc_driver_jar` in your config as usual (see [below](#whats-handled-automatically)). Either way, you point the tool at your database and your config file exactly as before — the difference is entirely in how the tool itself runs, not in what it produces.

---

## One-time setup

This image is not (yet) published on Docker Hub — every collaborator builds it themselves, once, from a clone of this repository:

```bat
:: from anywhere — build.cmd finds the repo root itself
docker\build.cmd
```
```bash
# from anywhere — build.sh finds the repo root itself
./docker/build.sh
```

(Everything needed — `Dockerfile`, `docker-entrypoint.sh`, `LICENSE_AGREEMENT.txt`, and `orm_skyway.py` — is already in this one repository; `orm_skyway.py` lives at the repo root so non-Docker users can grab just that one file, while the Docker-specific pieces live in `docker/`.) Once a private Docker Hub repository is set up, this step becomes a `docker pull` instead, and most collaborators won't need to build at all — the day-to-day usage below won't change either way.

> **macOS/Linux:** if you get `permission denied`, the executable bit was likely lost in transit (e.g. zipped on Windows, emailed). Either run `bash docker/build.sh` instead, or fix it once with `chmod +x docker/build.sh docker/run_orm_skyway.sh`.

---

## Day-to-day usage

From your project root directory — same place you'd normally run `orm_skyway.py`:

```bat
:: Windows
run_orm_skyway.cmd -f orm_skyway_config.json --phase 1+3
```

```bash
# macOS / Linux
./run_orm_skyway.sh -f orm_skyway_config.json --phase 1+3
```

Same config file, same flags, same interactive prompts as the standard workflow — see [Phase 1](begin_reverse_engineering.md), [Phase 2](orm_refinement.md), and [Phase 3](gilhari_microservice_packaging.md) for what each step does; none of that changes. `run_orm_skyway.sh`/`.cmd` just wraps `docker run` with the mounts the tool needs:

- your project directory, so generated files land where you expect
- the Docker socket, so Phase 3's `docker build` can run from inside the container, building on your host's Docker daemon
- (Linux/Colima only) `host.docker.internal` host-gateway resolution

---

## What's handled automatically

| You don't need to... | Because... |
|---|---|
| Set `jx_home` | The image's bundled JDX SDK is used automatically |
| Find a JDBC driver JAR for MySQL/PostgreSQL/SQLite | The image already has them |
| Worry about `localhost` in `jdbc_url` | Automatically resolved to reach your host machine's database |
| Edit anything for a SQLite file under your project directory | The whole project directory is already mounted |

Using a different database, or want to use a specific JDBC driver version rather than the one bundled in the image? Set `jdbc_driver_jar` in `orm_skyway_config.json` to its location as usual — see the [Configuration reference](configuration.md#database-connection-phase-1). A path under your project directory (e.g. `./config/your-driver.jar`) works the same way it does for a SQLite database file, since the whole project directory is mounted into the container.

A database on a remote server, or another Docker container by name, works exactly as it does outside Docker mode — no special handling needed either way.

> **Note:** this only affects how *the `orm_skyway.py` tool itself* runs (Phase 1 and Phase 3). The Gilhari microservice it produces, and how you run/test it in Phase 4, are unaffected — see [Phase 4 — Run and Test](gilhari_testing.md) as usual.

---

## The one thing still required locally: a JDK, for `JDXDemo`

[`JDXDemo`](orm_refinement.md#verifying-with-jdxdemo) is a graphical tool, and graphical tools can't run inside a Docker container — there's no display to draw to. To use `JDXDemo.bat`/`.sh` after Phase 1, you need a JDK on your own machine.

If you don't have the JDX SDK installed locally either, the tool offers to set up a small `jdx_sandbox/` folder in your project the first time it's needed — just say yes when asked. That gets you the JDX classes and license; you'll still need *some* JDK already on your machine for `java`/`javac` to work.

If you don't use `JDXDemo`, none of this applies to you.

---

## If your database file lives outside the project directory

This only matters for file-based databases (SQLite, etc.) whose file is *not* somewhere under your project root. If it is under the project root — the common case — skip this section entirely.

Set an environment variable before running, pointing at the real location, and reference the container-side path in your config:

```bat
set ORM_SKYWAY_EXTRA_MOUNT=C:\data:/extra_data
run_orm_skyway.cmd -f orm_skyway_config.json
```
```json
"jdbc_url": "jdbc:sqlite:/extra_data/mydb.sqlite"
```

(`ORM_SKYWAY_EXTRA_MOUNT=/data:/extra_data` on macOS/Linux.)

---

## A harmless warning you may see

`docker build` may print a `legacy builder is deprecated` message. It doesn't affect anything — the build completes normally either way.

---

## Licensing

`orm_skyway.py` itself is governed by `LICENSE_Skyway`. Separately, the `softwaretree/orm_skyway` image is built on `softwaretree/gilhari`, so it also carries Gilhari's own license terms — these are shown once, interactively, the first time you run the image against a given project directory (acceptance is recorded in that project so you won't see it again on later runs there).

---

← [README](../README.md)
