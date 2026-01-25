#!/usr/bin/env python3
import argparse
import json
import re
import uuid
from pathlib import Path

from utils import clean_solps_run_dir, compress_and_remove_run_dir
from rewrite_params import convert_params_file  # uses your existing rewrite script


def _read_json(p: Path):
    with p.open("r") as f:
        return json.load(f)


def _write_json(p: Path, obj):
    with p.open("w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def _patch_params_after_rename(params_path: Path, new_case_id: str, new_run_dir: Path):
    """Update case_id + location.path after directory rename."""
    meta = _read_json(params_path)

    meta.setdefault("case", {})
    meta["case"]["case_id"] = new_case_id
    meta.setdefault("case", {}).setdefault("location", {})
    meta["case"]["location"]["path"] = str(new_run_dir)

    # hard enforce your new core key
    core = meta.setdefault("inputs", {}).setdefault("core", {})
    if "particle_flux_s-1" in core and "density_m-3" not in core:
        core["density_m-3"] = core["particle_flux_s-1"]
    core.pop("particle_flux_s-1", None)

    _write_json(params_path, meta)


def parse_args():
    p = argparse.ArgumentParser(
        description="Finalize a legacy run dir: rewrite params.json, cleanup, rename, compress (using utils.py)."
    )
    p.add_argument("--run-dir", required=True, help="Path to legacy run dir (e.g. .../run_4p289_...)")
    p.add_argument("--label", default="D_C_Ne", help="Label used in final name (default: D_C_Ne)")
    p.add_argument("--uuid8", default=None, help="Optional 8-hex id. If omitted, generate.")
    p.add_argument("--apply", action="store_true", help="Actually perform actions (otherwise dry-run).")

    # rewrite_params behavior knobs
    p.add_argument("--backup-suffix", default=".bak", help="Backup suffix for params.json rewrite (default: .bak)")
    p.add_argument("--campaign", default="", help="campaign string to write into params.json")

    # cleanup/compress knobs
    p.add_argument("--keep-output", action="store_true", help="Keep output/ dir (otherwise removed)")
    p.add_argument("--zstd-level", type=int, default=19, help="zstd compression level (default: 19)")
    p.add_argument("--no-compress", action="store_true", help="Do not compress (stop after rename)")
    return p.parse_args()


def main():
    args = parse_args()
    run_path = Path(args.run_dir).expanduser().resolve()

    if not run_path.is_dir():
        raise SystemExit(f"Not a directory: {run_path}")

    # Pick / validate uuid8
    run_id = (args.uuid8 or uuid.uuid4().hex[:8]).lower()
    if not re.fullmatch(r"[0-9a-f]{8}", run_id):
        raise SystemExit(f"--uuid8 must be 8 hex chars. Got: {run_id}")

    case_id = f"{run_id}__{args.label}"
    new_dirname = f"run_{case_id}"
    new_path = run_path.parent / new_dirname

    params_path = run_path / "params.json"
    if not params_path.exists():
        raise SystemExit(f"Missing params.json: {params_path}")

    print(f"[0] input  : {run_path}")
    print(f"[0] output : {new_path}")
    print(f"[0] case_id: {case_id}")

    # 1) Rewrite params.json (old -> new). Uses your rewrite_params.py logic.
    did, msg = convert_params_file(
        params_path=params_path,
        apply=args.apply,
        backup_suffix=args.backup_suffix,
        label=args.label,
        campaign=args.campaign,
    )
    print(f"[1] rewrite: {msg}")

    # 2) Cleanup (your canonical function)
    removed = clean_solps_run_dir(
        str(run_path),
        remove_output_dir=(not args.keep_output),
        dry_run=(not args.apply),
    )
    print(f"[2] cleanup: {'would_remove' if not args.apply else 'removed'}={len(removed)}")

    if not args.apply:
        print("[dry-run] stopping before rename/patch/compress")
        return

    # 3) Rename folder
    if new_path.exists():
        raise SystemExit(f"Target already exists: {new_path}")
    run_path.rename(new_path)
    print(f"[3] rename : OK -> {new_path.name}")

    # 4) Patch params.json to reflect rename + enforce new keys
    new_params_path = new_path / "params.json"
    _patch_params_after_rename(new_params_path, new_case_id=case_id, new_run_dir=new_path)
    print("[4] patch  : updated case_id + location.path + dropped legacy core key")

    # 5) Compress (your canonical function makes <dir>.tar.zst and removes the dir)
    if not args.no_compress:
        archive = compress_and_remove_run_dir(str(new_path), level=args.zstd_level)
        print(f"[5] archive: {archive}")
    else:
        print("[5] archive: skipped (--no-compress)")


if __name__ == "__main__":
    main()


#python3 finalize_legacy_run.py --run-dir /Users/42d/run_2p000_1p700_2p000_0p300_1p000 --apply
