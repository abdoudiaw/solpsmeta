# solpsmeta  ORNL SOLPS metadata builder 


Utilities for building SOLPS-ITER case metadata (`params.json`) and running ensembles ( [LibEnsemble library](https://libensemble.readthedocs.io/en/main/index.html) )
for SOLPS-ITER parameter scans.

This repo provides:
- A **metadata schema** (`solpsmeta`)
- Helpers to create SOLPS run directories from templates
- Tools to **edit SOLPS input files** from metadata
- Example workflows:
  - Generate a single `params.json` (`case.py`)
  - Launch an **ensemble scan** with libEnsemble (`examples/runners/run_libe_solps.py`)

---

## Installation

Clone and install in editable mode:

```bash
git clone <YOUR_REPO_URL> solpsmeta
cd solpsmeta

python3 -m venv venv
source venv/bin/activate
pip install -U pip

pip install -e .

# Examples

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
