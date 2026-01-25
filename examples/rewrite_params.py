#!/usr/bin/env python3
"""
rewrite_params.py

Convert legacy SOLPS params.json format:

{
  "solps-iter-params": [
    {
      "machine": "DIIID",
      "case_id": "...",
      "gas_puff": ...,
      "Pe": ...,
      "Pi": ...,
      "core_flux": ...,
      "dna": ...,
      "hci": ...,
      "hce": ...,
      "authors": [...],
      "owner": "...",
      "converged": false,
      "date": "YYYY-MM-DD",
      "notes": "..."
    }
  ]
}

into a new-style schema compatible with your current tooling
(utils._safe_get paths, sqlite indexing, nearest queries, etc.).

Safe by default:
- Does NOT overwrite unless --apply is passed.
- Makes a backup copy when overwriting.
- Can run on one folder first.

Usage (single-case test):
  python3 rewrite_params.py --one "/path/to/SOLPS DB/run_1p322_..." --apply

Dry-run preview:
  python3 rewrite_params.py --one "/path/to/SOLPS DB/run_1p322_..."

Bulk (all run_* under root):
  python3 rewrite_params.py --root "/path/to/SOLPS DB" --apply
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


DEFAULT_LABEL = "D_C_Ne"   # matches your current ensemble species label convention
DEFAULT_CAMPAIGN = ""      # you can set e.g. "174310_LDRD" if you want


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_date_ymd(s: str) -> Optional[str]:
    """Return ISO timestamp-like string from YYYY-MM-DD, else None."""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.strptime(s.strip(), "%Y-%m-%d")
        return dt.isoformat(timespec="seconds")
    except Exception:
        return None


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r") as f:
        return json.load(f)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def _detect_old_format(d: Dict[str, Any]) -> bool:
    return isinstance(d, dict) and "solps-iter-params" in d and isinstance(d["solps-iter-params"], list)


def _case_id_from_dir(run_dir: Path) -> str:
    name = run_dir.name
    return name.replace("run_", "", 1) if name.startswith("run_") else name


def convert_old_to_new(
    old_entry: Dict[str, Any],
    run_dir: Path,
    label: str = DEFAULT_LABEL,
    campaign: str = DEFAULT_CAMPAIGN,
) -> Dict[str, Any]:
    """
    Build the minimal "new schema" that your current code reads:
      machine, campaign,
      case.case_id, case.location.path, case.label, case.created_ts, case.status.converged, case.authors,
      inputs.gas_puffing.targets.{D2,Ne}.value,
      inputs.power.{Pe_W,Pi_W},
      inputs.core.particle_flux_s-1,
      inputs.transport.{dna,hci,hce}.value
    """
    machine = old_entry.get("machine", "") or ""
    # normalize common spelling
    if machine.upper() in {"DIIID", "DIII D", "DIII-D"}:
        machine = "DIII-D"

    case_id = old_entry.get("case_id") or _case_id_from_dir(run_dir)

    # Old: gas_puff is your D puff (D2). Ne puff was 0 back then.
    puff_d2 = float(old_entry.get("gas_puff", 0.0) or 0.0)
    puff_ne = float(old_entry.get("puff_ne", 0.0) or 0.0)  # if it ever exists, use it

    # Old Pe/Pi appear to already be Watts in your example (~7.6e6 W).
    pe_w = float(old_entry.get("Pe", 0.0) or 0.0)
    pi_w = float(old_entry.get("Pi", 0.0) or 0.0)

    core_flux = float(old_entry.get("core_flux", 0.0) or 0.0)
    dna = float(old_entry.get("dna", 0.0) or 0.0)
    hci = float(old_entry.get("hci", 0.0) or 0.0)
    hce = float(old_entry.get("hce", hci) or hci)

    authors = old_entry.get("authors", []) or []
    owner = old_entry.get("owner", "") or ""
    notes = old_entry.get("notes", "") or ""

    created_ts = _parse_date_ymd(old_entry.get("date", "")) or _iso_now()
    converged = bool(old_entry.get("converged", False))

    new_meta: Dict[str, Any] = {
        "schema": "solps-case-v2-min",  # arbitrary label; your readers don't require it
        "machine": machine,
        "campaign": campaign,
        "case": {
            "case_id": str(case_id),
            "label": label,
            "created_ts": created_ts,
            "authors": authors,
            "owner": owner,
            "notes": notes,
            "location": {"path": str(run_dir)},
            "status": {"converged": converged},
        },
        "inputs": {
            "time_dependence": {"mode": "steady_state"},
            "gas_puffing": {
                "targets": {
                    "D2": {"value": puff_d2, "gpfc": [2, 0, 0]},
                    "Ne": {"value": puff_ne, "gpfc": [0, 0, 1]},
                }
            },
            "power": {"Pe_W": pe_w, "Pi_W": pi_w},
            "core": {"density_m-3": core_flux},
            "transport": {
                "units": "SI",
                "slots": 20,
                "dna": {"type": "global", "value": dna},
                "hci": {"type": "global", "value": hci},
                "hce": {"type": "global", "value": hce},
            },
        },
        # Keep some provenance breadcrumbs (optional but handy)
        "provenance": {
            "converted_from": "legacy-solps-iter-params",
            "converted_ts": _iso_now(),
        },
    }
    return new_meta


def convert_params_file(
    params_path: Path,
    apply: bool,
    backup_suffix: str = ".bak",
    label: str = DEFAULT_LABEL,
    campaign: str = DEFAULT_CAMPAIGN,
) -> Tuple[bool, str]:
    """
    Returns (did_convert, message).
    """
    run_dir = params_path.parent
    try:
        data = _read_json(params_path)
    except Exception as e:
        return False, f"READ_FAIL: {params_path} ({e})"

    if _detect_old_format(data):
        old_list = data.get("solps-iter-params", [])
        if not old_list:
            return False, f"SKIP_EMPTY_OLD: {params_path}"
        old_entry = old_list[0]
        new_meta = convert_old_to_new(old_entry, run_dir=run_dir, label=label, campaign=campaign)

        if not apply:
            return True, f"DRYRUN would rewrite: {params_path}"

        # backup then overwrite
        backup = params_path.with_name(params_path.name + backup_suffix)
        if not backup.exists():
            shutil.copy2(params_path, backup)

        _write_json(params_path, new_meta)
        return True, f"OK rewrote: {params_path} (backup: {backup.name})"

    # already new? leave it alone
    return False, f"SKIP_NOT_OLD: {params_path}"


def iter_run_dirs(root: Path):
    for p in sorted(root.glob("run_*")):
        if p.is_dir():
            yield p


def parse_args():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--one", help="Convert a single run directory (e.g. .../SOLPS DB/run_...)")
    g.add_argument("--root", help="Convert all run_* dirs under this root")
    ap.add_argument("--params-name", default="params.json", help="Filename to convert (default: params.json)")
    ap.add_argument("--apply", action="store_true", help="Actually write changes (otherwise dry-run)")
    ap.add_argument("--backup-suffix", default=".bak", help="Backup suffix when overwriting (default: .bak)")
    ap.add_argument("--label", default=DEFAULT_LABEL, help=f"case.label to write (default: {DEFAULT_LABEL})")
    ap.add_argument("--campaign", default=DEFAULT_CAMPAIGN, help="campaign string to write (default: empty)")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N (bulk mode)")
    return ap.parse_args()


def main():
    args = parse_args()
    processed = 0
    converted = 0

    if args.one:
        run_dir = Path(args.one).expanduser().resolve()
        params_path = run_dir / args.params_name
        if not params_path.exists():
            print(f"ERROR: not found: {params_path}")
            raise SystemExit(2)
        did, msg = convert_params_file(
            params_path,
            apply=args.apply,
            backup_suffix=args.backup_suffix,
            label=args.label,
            campaign=args.campaign,
        )
        print(msg)
        if did:
            converted += 1
        processed += 1

    else:
        root = Path(args.root).expanduser().resolve()
        if not root.exists():
            print(f"ERROR: root not found: {root}")
            raise SystemExit(2)

        for run_dir in iter_run_dirs(root):
            if args.limit and processed >= args.limit:
                break
            params_path = run_dir / args.params_name
            if not params_path.exists():
                processed += 1
                print(f"SKIP_NOFILE: {params_path}")
                continue

            did, msg = convert_params_file(
                params_path,
                apply=args.apply,
                backup_suffix=args.backup_suffix,
                label=args.label,
                campaign=args.campaign,
            )
            print(msg)
            if did:
                converted += 1
            processed += 1

    print(f"\nSummary: processed={processed}, converted_or_would_convert={converted}, apply={args.apply}")


if __name__ == "__main__":
    main()

