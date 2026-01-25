#!/usr/bin/env python3
import os, json, uuid, argparse
from datetime import datetime
from solpsmeta import SpeciesSpec, meta_builder, _coerce_species, _species_label, _git_info

import subprocess


def parse_args():
    p = argparse.ArgumentParser(description="Create a SOLPS params.json (no run, no edits)")
    p.add_argument("--out-dir", default=".", help="Directory where params.json will be written")
    p.add_argument("--case-id", default=None, help="Optional explicit case_id. If omitted, auto-generate.")

    # Inputs (match your sim_f vector meaning)
    p.add_argument("--puff-d2", type=float, required=True)
    p.add_argument("--puff-ne", type=float, required=True)
    p.add_argument("--p-w", type=float, required=True, help="Total power [W]")
    p.add_argument("--core-density", type=float, required=True)
    p.add_argument("--dna", type=float, required=True)
    p.add_argument("--hci", type=float, required=True)

    # Metadata
    p.add_argument("--machine", default="DIII-D")
    p.add_argument("--campaign", default="174310_LDRD")
    p.add_argument("--owner", default="ORNL")
    p.add_argument("--notes", default="case.py generated")
    p.add_argument("--solps-repo", default=os.getenv("SOLPS_REPO", ""),
                   help="Path to solps-iter git repo (for provenance)")
    p.add_argument("--solps-version", default=os.getenv("SOLPS_VERSION", ""),
                   help="Optional manual SOLPS version label")


    return p.parse_args()

def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Species (same as your ensemble)
    species = SpeciesSpec(
        main_ion="D",
        impurities=["C", "Ne"],
        charge_state_ranges={"D": [0, 1], "C": [0, 6], "Ne": [0, 10]},
    )
    label = _species_label(species)

    run_id = uuid.uuid4().hex[:8]
    case_id = args.case_id or f"{run_id}__{label}"

    # Split power
    Pe_W = 0.5 * args.p_w
    Pi_W = 0.5 * args.p_w

    puff_targets = {
        "D2": {"value": args.puff_d2, "gpfc": [2, 0, 0]},
        "Ne": {"value": args.puff_ne, "gpfc": [0, 0, 1]},
    }

    transport = {
        "units": "SI",
        "slots": 20,
        "dna": {"type": "global", "value": args.dna},
        "hci": {"type": "global", "value": args.hci},
        "hce": {"type": "global", "value": args.hci},
    }

    spec = meta_builder(
        machine=args.machine,
        campaign=args.campaign,
        time_dependence={"mode": "steady_state"},
        case_id=case_id,
        run_dir=out_dir,   # we are NOT creating a run dir; just recording where params.json lives
        authors=["A. Diaw"],
        owner=args.owner,
        species=_coerce_species(species),
        puff_targets=puff_targets,
        Pe_W=Pe_W,
        Pi_W=Pi_W,
        core_density=args.core_density,
        transport=transport,
        notes=args.notes,
        converged=False,
    )

    # Extra provenance
    spec["case"]["run_id"] = run_id
    spec["case"]["label"] = label
    spec["case"]["created_ts"] = datetime.now().isoformat(timespec="seconds")
    spec["provenance"]["code"]["solps_version"] = args.solps_version or ""
    if args.solps_repo:
        spec["provenance"]["code"]["git"] = _git_info(args.solps_repo)


    out_path = os.path.join(out_dir, f"params.json")
    with open(out_path, "w") as f:
        json.dump(spec, f, indent=2)

    print("✅ wrote", out_path)
    print("case_id =", case_id)

if __name__ == "__main__":
    main()


#python3 case.py \
#  --out-dir ./case_test \
#  --puff-d2 2.5e21 \
#  --puff-ne 1e19 \
#  --p-w 4e6 \
#  --core-density 7.5e20 \
#  --dna 1.067 \
#  --hci 0.62 \
#  --solps-repo /Users/42d/solps-iter \
#  --solps-version "SOLPS-ITER local build"
