from build_metadata_v2 import build_metadata_v2, SpeciesSpec
from builder import make_case_from_template, apply_edits
import os, json


warm_start_dir = "case0"          # your template folder
out_root = os.getcwd()               # where run_* dirs go

# -----------------------------
# 1) choose your species registry
# -----------------------------
species = SpeciesSpec(
    main_ion="D",
    impurities=["C", "Ne"],
    charge_state_ranges={
        "D":  [0, 1],
        "C":  [0, 6],
        "Ne": [0, 10]
    }
)

# -----------------------------
# 2) define the case parameters
# -----------------------------
case_id = "3p416_4p175_1p461_1p067_0p620"

puff_targets = {
  "D2": {"value": 2.5e21, "gpfc": [2, 0, 0]},
  "Ne": {"value": 1.0e19, "gpfc": [0, 0, 1]}
}

transport = {
    "units": "SI",
#    "dna": {"type": "per_species", "values": {"D": 1.06714976, "C": 1.06714976, "Ne": 1.06714976}},
#    "hci": {"type": "per_species", "values": {"D": 0.62026092, "C": 0.62026092, "Ne": 0.62026092}},
    "dna": {"type": "global", "value": 1.06714976},
    "hci": {"type": "global", "value": 0.62026092},
    "hce": {"type": "global", "value": 0.62026092},
}

# -----------------------------
# 3) create the run directory
# -----------------------------
run_dir = make_case_from_template(
    warm_start_dir=warm_start_dir,
    out_root=out_root,
    case_id=case_id
)

# -----------------------------
# 4) build metadata JSON
# -----------------------------
spec = build_metadata_v2(
    machine="DIII-D",
    campaign="174310_LDRD",
    time_dependence={"mode": "steady_state"},
    case_id=case_id,
    run_dir=run_dir,
    authors=["A. Diaw", "J. Lore", "J.S. Park", "S. De Pascuale"],
    owner="ORNL",
    species=species,
    puff_targets=puff_targets,
    Pe_W=4.1748614e6,
    Pi_W=2.1748614e6,
    core_flux=1.46100463e20,
    transport=transport,
    notes="test case",
    converged=False,
)

# -----------------------------
# 5) write params.json
# -----------------------------
with open(os.path.join(run_dir, "params.json"), "w") as f:
    json.dump(spec, f, indent=2)

# -----------------------------
# 6) edit SOLPS input files using that JSON
# -----------------------------
apply_edits(run_dir, spec)

print("✅ Case created:", run_dir)

