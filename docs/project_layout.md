# Project Layout

_Last updated: 2026-07-16_

← [README](../README.md)

The script always runs from your **project root directory** — whichever directory you `cd` into before running it. All artifacts are created beneath that directory.

The tool repo (`orm_skyway_automation/`) and your service project directories are completely independent. Clone the tool once to a convenient location and reference it from as many projects as you like.

---

## Full directory tree

```
<project root>/
│
│   orm_skyway_config.json     ← your input config (edit this)
│   sources.txt                         ← Java source list for javac
│   .gitignore                          ← excludes credentials, binaries, logs
│   .gitattributes                      ← enforces correct line endings in Git
│   .dockerignore                       ← excludes DB file from Docker build context (Phase 3, file-based DBs only)
│
├── scripts/                            ← Phase 1 helper scripts
│       setEnvironment.bat / .sh            ← sets JX_HOME and CLASSPATH
│       JDXReverseEngineer.bat / .sh        ← runs JDXSchema manually if needed
│       compile.bat / .sh                   ← compiles model classes (cleans bin/ first)
│       JDXDemo.bat / .sh                   ← local model verification tool
│
├── gilhari/                             ← Phase 3 Gilhari build-time/runtime artifacts
│       gilhari_service.config              ← Gilhari runtime config
│       Dockerfile                          ← Docker image definition
│       build.cmd / build.sh                ← docker build
│       run_docker_app.cmd / .sh            ← docker run
│       sampleCurlCommands.cmd / .sh              ← read-only sample REST calls
│       sampleCurlWriteCommands.cmd / .sh         ← write-op sample REST calls (commented out)
│       connectORMCP.md                     ← ORMCP connection guide
│       curl.log                            ← sample-curl-script output, if invoked from here (git-ignored)
│
├── config/
│       <n>.config                      ← reverse-engineering template (Phase 1 input)
│       <n>.config.revjdx               ← auto-generated ORM spec (do not edit)
│       <n>.config.jdx                  ← working ORM spec (edit in Phase 2)
│       <n>.config.docker.jdx           ← Docker copy (auto-generated in Phase 3)
│       JDXDemo.config                  ← JDXDemo configuration
│       classnames_map.json             ← short class name → FQN map (Phase 3)
│       <jdbc-driver>.jar               ← JDBC driver copy (for Docker packaging)
│
├── src/
│   └── com/example/json/model/
│           Employee.java               ← generated container model classes
│           Department.java
│           ...
│
└── bin/
    └── com/example/json/model/
            Employee.class              ← compiled classes
            Department.class
            ...
```

Where `<n>` is the value of `reverse_eng_template_config` in your config file (default: `reverse_eng_template`).

---

## Why `scripts/` and `gilhari/`

Earlier versions wrote all 16 generated script/artifact files directly into the project root, alongside `orm_skyway_config.json` and the Git config files — cluttering the one directory you look at most. `scripts/` and `gilhari/` are now siblings of `src/`, `bin/`, and `config/`, grouped by which phase generates them:

- **`scripts/`** — general, DB-independent helper scripts from Phase 1 (`setEnvironment`, `JDXReverseEngineer`, `compile`, `JDXDemo`).
- **`gilhari/`** — everything specific to packaging and running the Gilhari microservice, from Phase 3.

A few things worth knowing about how this works:

- **Every generated script self-locates to the project root before doing anything else** (`cd "$(dirname "$0")/.."` in `.sh`, `cd /d "%~dp0.."` in `.bat`/`.cmd`), so they behave the same regardless of where they're invoked from — you don't need to `cd` into `scripts/` or `gilhari/` first.
- **`scripts/` and `gilhari/` are never wiped (`rmtree`'d) on rerun**, unlike `src/` and `bin/`. Both directories hold a fixed, known set of filenames that are fully overwritten by name every run — there's no orphan-file risk the way there is for schema-dependent generated code, so a full-directory clean isn't needed. It's also safer: you can drop your own notes or variant scripts into either directory without a rerun deleting them.
- **The Docker build context is still the project root**, even though `Dockerfile` now lives in `gilhari/`. `build.cmd`/`build.sh` invoke `docker build -f gilhari/Dockerfile .` — the `-f` flag points at the Dockerfile's new location, while `.` (the context) stays root so `ADD bin ./bin` and `ADD config ./config` keep working unchanged.
- **`.dockerignore` deliberately stays at project root, not in `gilhari/`.** Docker looks for `.dockerignore` relative to the build *context* directory, not next to the Dockerfile — moving it into `gilhari/` would cause it to be silently ignored, and DB files intended for exclusion could leak into the image.
- **`sources.txt` also stays at project root**, not in `scripts/`. Since `compile.bat`/`.sh` `cd` to root before running, `find src -name "*.java" > sources.txt` (and its `.bat` equivalent) still lands it at root, exactly as before.

---

## The three ORM spec files

| File | URL in connection string | Who uses it | Edit? |
|---|---|---|---|
| `<n>.config.revjdx` | `localhost` | Immutable auto-generated record | Never |
| `<n>.config.jdx` | `localhost` | Your working copy — JDXDemo, local Java apps, Phase 2 editing | Yes |
| `<n>.config.docker.jdx` | `host.docker.internal` | Packaged inside the Docker image | Never (regenerated by Phase 3) |

The `.docker.jdx` uses `host.docker.internal` instead of `localhost` because inside a Docker container, `localhost` refers to the container itself, not your host machine. The working `.jdx` keeps `localhost` so local tools like JDXDemo continue to work unchanged.

---

## Git configuration files

Phase 3 generates two Git configuration files in the project root. Neither is required for the tool to work — they are provided as a convenience for users who commit their generated project to version control.

**`.gitignore`** — excludes files that should not be committed:
- `bin/` — compiled Java classes (regenerated by `scripts/compile.bat` / `compile.sh`)
- `config/*.jdx`, `config/*.revjdx`, `config/*.docker.jdx` — ORM spec files contain database credentials
- `config/<jdbc-driver>.jar` — large binary, project-specific
- `curl.log` — curl output log (lands wherever the sample curl script is invoked *from* — e.g. `gilhari/curl.log` if run as `gilhari\sampleCurlCommands.cmd` from root, or project root if run as `.\sampleCurlCommands.cmd` after `cd gilhari`; the bare `curl.log` pattern matches it at any depth either way)
- `orm_skyway_config.json` — may contain credentials

> Running via [Docker mode](docker_mode.md) adds two more excluded entries: `.orm_skyway_license_accepted` and `jdx_sandbox/` — both local/machine-specific, regenerated automatically when needed.

**`.gitattributes`** — enforces correct line endings when files are committed from any platform:
- `*.sh` → LF — shell scripts must have Unix line endings to run on macOS/Linux. Without this, scripts committed from Windows get CRLF endings and fail with `bad interpreter: No such file or directory`.
- `*.bat`, `*.cmd` → CRLF — Windows batch files expect CRLF
- `*.java`, `*.json`, `*.md`, `*.jdx`, `*.config` → LF
- `*.jar`, `*.class`, `*.db` → binary (no conversion)

These patterns apply regardless of directory depth, so they cover `scripts/*.bat` and `gilhari/*.cmd` the same as if the files were still at root — no changes were needed to `.gitattributes` when these directories were introduced.

> **Windows note:** If you commit from Windows, also run:
> ```bat
> git config --system core.autocrlf false
> ```
> (requires Administrator) to prevent Git for Windows from overriding `.gitattributes` and re-introducing CRLF on checkout.

Both files are only written if they do not already exist — existing files are never overwritten.

---

## Why `scripts/*.bat` but `gilhari/*.cmd`

You'll notice `scripts/` uses the `.bat` extension throughout, while `gilhari/` uses `.cmd`. This is intentional, not inconsistent: it reflects each product's own convention. JDX is the older product and its tooling has always shipped `.bat` scripts; Gilhari is newer and adopted `.cmd`. Keeping that split makes each directory's scripts recognizable to anyone already familiar with JDX or Gilhari repositories elsewhere. Functionally the two extensions behave identically on modern Windows (both run under `cmd.exe`), so this is a naming convention only.

---

## Key design decisions

**Project root = current working directory.** There is no `output_dir` setting. Running the script from the project directory keeps the layout predictable and matches standard JDX/Gilhari conventions.

**`bin/<pkg>/` is cleaned before every compile.** Removes stale `.class` files for classes dropped from the `.jdx` during Phase 2, preventing them from ending up in the Docker image.

**`src/<pkg>/` is cleaned before every reverse-engineering run.** Removes `.java` files from a previous run with a different table selection. If you have hand-edited any `.java` files, save copies before re-running Phase 1.

**`scripts/` and `gilhari/` are never fully cleaned, only overwritten file-by-file.** Both hold a fixed, known set of generated filenames — unlike `src/`/`bin/`, there's no schema-dependent orphan-file risk, so a directory-level `rmtree` isn't necessary or safe to assume.

**Class names are discovered from `bin/` in Phase 3, not from the database.** Reflects the actual post-Phase-2 compiled state; no database connection is required.

**`src/` is not packaged in the Docker image.** Only the compiled `bin/` is needed at runtime.

---

← [README](../README.md)
