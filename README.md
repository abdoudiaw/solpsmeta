# solpsmeta — ORNL SOLPS-ITER metadata builder

Utilities for building SOLPS-ITER case metadata (`params.json`) and running ensemble parameter scans using
[libEnsemble](https://libensemble.readthedocs.io/en/main/index.html).

GitHub: https://github.com/abdoudiaw/solpsmeta

---

## What this repository provides

- A SOLPS metadata schema + helpers to generate `params.json`
- Helpers to create SOLPS run directories from templates
- Tools to **edit SOLPS input files** from metadata
- End-to-end example workflows:
  - Build a single metadata file (`examples/case.py`)
  - Launch an ensemble scan (`examples/runners/run_libe_solps.py`)

---

## Repository layout

- `solpsmeta/`  
  Python library (schema + metadata builder + input file editors)

- `examples/case.py`  
  Generate a single `params.json` (metadata only; does not run SOLPS)

- `examples/runners/`  
  libEnsemble workflow to generate + run many SOLPS cases:
  - `run_libe_solps.py` : main launcher
  - `sim_f_solps.py`    : per-case simulation function
  - `utils.py`          : watcher thread + cleanup/compression utilities

---

## Installation

Clone and install in editable mode:

```bash
git clone https://github.com/abdoudiaw/solpsmeta.git
cd solpsmeta

python3 -m venv venv
source venv/bin/activate
pip install -U pip

pip install -e .
````

If needed, install extra requirements:

```bash
pip install -r requirements.txt
```

---

## Quick start

### 1) Build a single SOLPS metadata file (`params.json` only)

This does **NOT** run SOLPS. It only builds a metadata file describing a SOLPS case.

```bash
cd examples

python3 case.py \
  --out-dir ./case_test \
  --puff-d2 2.5e21 \
  --puff-ne 1e19 \
  --p-w 4e6 \
  --core-flux 7.5e20 \
  --dna 1.067 \
  --hci 0.62 \
  --notes "single case metadata only"
```

Output:

* `examples/case_test/params.json`

To see all options:

```bash
python3 case.py -h
```

---

### 2) Launch an ensemble scan with libEnsemble

The ensemble runner will create an output directory:

```
ens__DIII-D__174310_LDRD__D_C_Ne__ss__lhs__YYYYMMDD_HHMMSS/
```

Inside it, you get:

* `run_<case_id>/` directories for each case
* each `run_<case_id>/` contains:

  * `params.json`
  * edited SOLPS input files
  * `run.log`
  * `.done.json` marker (when complete)
* `ensemble_meta.json` at the root

---

## Running the ensemble runner

### Recommended first test: Dry-run

Dry-run replaces SOLPS executable with `/bin/echo` to test the pipeline quickly.

```bash
cd examples/runners

python3 run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --dry-run \
  --sim-max 4 --nworkers 2 --batch 2
```

---

### Real SOLPS run

```bash
cd examples/runners

python3 run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --solps-exe b2mn_glibc \
  --np-ranks 40 \
  --sim-max 20 --nworkers 4 --batch 4
```

---

## Case builder (`examples/case.py`) options

This script generates only a `params.json`.

Show full help:

```bash
python3 examples/case.py -h
```

Typical usage:

```bash
python3 examples/case.py \
  --out-dir ./case_test \
  --case-id my_case_id__D_C_Ne \
  --machine DIII-D \
  --campaign 174310_LDRD \
  --owner ORNL \
  --notes "metadata only" \
  --puff-d2 2.5e21 \
  --puff-ne 1e19 \
  --p-w 4e6 \
  --core-flux 7.5e20 \
  --dna 1.067 \
  --hci 0.62
```

---

## Runner (`examples/runners/run_libe_solps.py`) options

Show full help:

```bash
python3 examples/runners/run_libe_solps.py -h
```

### Core run controls

* `--sim-max N`
  Total number of cases to run.

* `--batch N`
  LHS generation batch size.

* `--poll SECONDS`
  Watcher polling interval.

* `--nworkers N`
  Number of libEnsemble workers.

  * `0` means auto-select based on MPI ranks per case.

---

### Paths and SOLPS execution

* `--baserun-src PATH`
  Path to baserun template directory.

* `--warm-start-dir PATH`
  Warm-start SOLPS directory used to initialize each run.

* `--solps-exe EXE`
  SOLPS executable path or command name (default: `b2mn_glibc`).

* `--np-ranks N`
  Number of MPI ranks per SOLPS simulation.

* `--dry-run`
  Do not run SOLPS; use `/bin/echo` instead.

---

### Cleanup controls

Cleanup removes non-essential files from completed `run_*` folders.

* `--no-cleanup`
  Disable cleanup entirely.

* `--cleanup-dry-run`
  Print what cleanup would delete, but do not delete.

* `--cleanup-keep-output`
  Keep `run_*/output/` directory.

---

### Compression controls

Compression creates `.tar.zst` archives of completed runs and optionally deletes the original folder.

* `--no-compress`
  Disable compression and deletion of `run_*` folders.

* `--zstd-level N`
  zstd compression level (default: `19`)

---

## Common usage patterns

### A) Keep everything (no cleanup, no compression, no deletion)

```bash
python3 examples/runners/run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --no-cleanup \
  --no-compress \
  --sim-max 4 --nworkers 2 --batch 2
```

### B) Cleanup only (reduce folder size, but keep run directories)

```bash
python3 examples/runners/run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --no-compress \
  --sim-max 20 --nworkers 4 --batch 4
```

### C) Cleanup + compression (archive and remove run folders)

```bash
python3 examples/runners/run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --sim-max 20 --nworkers 4 --batch 4 \
  --zstd-level 19
```

---

## Environment variables (optional)

You may set environment variables instead of passing arguments:

```bash
export SOLPS_BASERUN_SRC=/PATH/TO/baserun
export SOLPS_WARM_START_DIR=/PATH/TO/warm_start_case
export SOLPS_EXE=b2mn_glibc
export SOLPS_NP_RANKS=40

export SOLPS_SIM_MAX=20
export SOLPS_NWORKERS=4
export SOLPS_GEN_BATCH=4
export SOLPS_POLL_S=1.0
```

Then run:

```bash
cd examples/runners
python3 run_libe_solps.py
```

Unset any variable:

```bash
unset SOLPS_EXE
```

---

## Running in background

### Simple background run

```bash
python3 examples/runners/run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --sim-max 20 --nworkers 4 --batch 4 \
  > run.log 2>&1 &
disown
```

### Using nohup

```bash
nohup python3 examples/runners/run_libe_solps.py \
  --baserun-src /PATH/TO/baserun \
  --warm-start-dir /PATH/TO/warm_start_case \
  --sim-max 20 --nworkers 4 --batch 4 \
  > run.log 2>&1 < /dev/null &
```

---

## Notes (macOS tar)

macOS default `tar` (BSD tar / bsdtar) does not support GNU tar option:

```
tar --sort=name
```

If compression is enabled and you see:

```
tar: Option --sort=name is not supported
```

Solutions:

* run with `--no-compress` (recommended on macOS), OR
* install GNU tar:

```bash
brew install gnu-tar
```

and configure compression to use `gtar`.

---

## Author / Maintainer

Abdourahmane (Abdou) Diaw (ORNL)

```

---

If you want, I can also generate a *shorter* README version (1 page) and keep this one as `docs/README_full.md`.
```

