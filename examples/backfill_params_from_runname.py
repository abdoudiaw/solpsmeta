#!/usr/bin/env python3
"""
backfill_params_from_runname.py

Create modern params.json for legacy run_* dirs that are missing params.json,
by decoding the five tokens in the directory name:

run_<puff>_<Pe(MW)>_<core_density(1e20)>_<dna>_<hci>

Example:
run_2p473_7p624_6p071_0p961_0p462

Scales (from your legacy params.json evidence):
  puff_d2      = token1 * 1e21
  Pe_W, Pi_W   = token2 * 1e6  (so p_w = 2*token2*1e6)
  core_density = token3 * 1e20
  dna          = token4
  hci          = token5

Safe by default: dry-run unless --apply.
"""

import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime

from solpsmeta import SpeciesSpec, meta_builder, _coerce_species, _species_label

TOKEN_RE = re.compile(
    r"^run_(?P<a>[\dp]+)_(?P<b>[\dp]+)_(?P<c>[\dp]+)_(?P<d>[\dp]+)_(?P<e>[\dp]+)$"
)

def tok_to_float(tok: str) -> float:
    # "2p473" -> 2.473
    return float(tok.replace("p", "."))

def build_params_for_dir(
    run_dir: Path,
    label_override: str,
    machine: str,
    campaign: str,
    owner: str,
    authors: list[str],
    notes: str,
    puff_ne_default: float,
) -> dict:
    m = TOKEN_RE.match(run_dir.name)
    if not m:
        raise ValueError(f"Run dir name does not match expected legacy pattern: {run_dir.name}")

    a = tok_to_float(m.group("a"))
    b = tok_to_float(m.group("b"))
    c = tok_to_float(m.group("c"))
    d = tok_to_float(m.group("d"))
    e = tok_to_float(m.group("e"))

    puff_d2 = a * 1e21
    Pe_W = b * 1e6
    Pi_W = b * 1e6
    core_density = c * 1e20
    dna = d
    hci = e
    puff_ne = puff_ne_default

    species = SpeciesSpec(
        main_ion="D",
        impurities=["C", "Ne"],
        charge_state_ranges={"D": [0, 1], "C": [0, 6], "Ne": [0, 10]},
    )
    label = label_override or _species_label(species)

    # Stable case_id for legacy dirs (so you can always trace it back)
    legacy_id = run_dir.name.replace("run_", "", 1)
    case_id = f"legacy__{legacy_id}__{label}"

    puff_targets = {
        "D2": {"value": puff_d2, "gpfc": [2, 0, 0]},
        "Ne": {"value": puff_ne, "gpfc": [0, 0, 1]},
    }

    transport = {
        "units": "SI",
        "slots": 20,
        "dna": {"type": "global", "value": dna},
        "hci": {"type": "global", "value": hci},
        "hce": {"type": "global", "value": hci},
    }

    spec = meta_builder(
        machine=machine,
        campaign=campaign,
        time_dependence={"mode": "steady_state"},
        case_id=case_id,
        run_dir=str(run_dir),
        authors=authors,
        owner=owner,
        species=_coerce_species(species),
        puff_targets=puff_targets,
        Pe_W=Pe_W,
        Pi_W=Pi_W,
        core_density=core_density,
        transport=transport,
        notes=notes,
        converged=False,
    )

    # some nice provenance breadcrumbs
    spec.setdefault("case", {})
    spec["case"]["created_ts"] = datetime.now().isoformat(timespec="seconds")
    spec.setdefault("provenance", {})
    spec["provenance"]["backfilled_from"] = "legacy_run_dir_name"
    spec["provenance"]["legacy_run_dir"] = str(run_dir)

    return spec

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, help="Root containing run_* dirs")
    p.add_argument("--apply", action="store_true", help="Write params.json (otherwise dry-run)")
    p.add_argument("--overwrite", action="store_true", help="Overwrite params.json if it exists")

    p.add_argument("--machine", default="DIII-D")
    p.add_argument("--campaign", default="APP-FPP")
    p.add_argument("--owner", default="ORNL")
    p.add_argument("--authors", default="A. Diaw", help="Comma-separated authors")
    p.add_argument("--label", default="D_C_Ne", help="case.label override (default D_C_Ne)")
    p.add_argument("--notes", default="backfilled from legacy run dir name")
    p.add_argument("--puff-ne-default", type=float, default=0.0)

    p.add_argument("--limit", type=int, default=0, help="Only process first N dirs")
    return p.parse_args()

def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    authors = [a.strip() for a in args.authors.split(",") if a.strip()]

    processed = 0
    created = 0
    skipped = 0

    for d in sorted(root.glob("run_*")):
        if args.limit and processed >= args.limit:
            break
        if not d.is_dir():
            continue

        params_path = d / "params.json"
        if params_path.exists() and not args.overwrite:
            skipped += 1
            processed += 1
            continue

        try:
            spec = build_params_for_dir(
                run_dir=d,
                label_override=args.label,
                machine=args.machine,
                campaign=args.campaign,
                owner=args.owner,
                authors=authors,
                notes=args.notes,
                puff_ne_default=args.puff_ne_default,
            )
        except Exception as e:
            print(f"skip_bad_name: {d.name} ({e})")
            processed += 1
            continue

        if not args.apply:
            print(f"dryrun: would_write {params_path}")
        else:
            with open(params_path, "w") as f:
                json.dump(spec, f, indent=2)
                f.write("\n")
            print(f"ok: wrote {params_path}")
            created += 1

        processed += 1

    print(f"\nSummary: processed={processed}, wrote={created}, skipped_existing={skipped}, apply={args.apply}")

if __name__ == "__main__":
    main()

