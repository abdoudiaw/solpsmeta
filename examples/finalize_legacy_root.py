#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from datetime import datetime

# Reuse your working per-run code by importing its functions
from finalize_legacy_run import main as finalize_one_main  # not used; we call underlying helpers instead
from finalize_legacy_run import _patch_params_after_rename
from rewrite_params import convert_params_file
from utils import clean_solps_run_dir, compress_and_remove_run_dir

import re
import uuid


def _write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


def parse_args():
    p = argparse.ArgumentParser(
        description="Bulk finalize legacy SOLPS run_* dirs: rewrite params, cleanup, rename, compress. Skip dirs without params.json."
    )
    p.add_argument("--root", required=True, help="Root directory containing run_* folders")
    p.add_argument("--label", default="D_C_Ne", help="Label used in final name (default: D_C_Ne)")
    p.add_argument("--apply", action="store_true", help="Actually perform actions (otherwise dry-run)")

    # behavior knobs
    p.add_argument("--backup-suffix", default=".bak")
    p.add_argument("--campaign", default="")
    p.add_argument("--keep-output", action="store_true")
    p.add_argument("--zstd-level", type=int, default=19)
    p.add_argument("--no-compress", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Process at most N run dirs (0 = no limit)")
    p.add_argument("--skip-if-archived", action="store_true",
                  help="Skip a run_* dir if a matching run_*.tar.zst already exists next to it")
    return p.parse_args()


def _gen_uuid8():
    return uuid.uuid4().hex[:8].lower()


def _is_uuid8(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{8}", s))


def finalize_one_dir(run_path: Path, *, label: str, apply: bool,
                     backup_suffix: str, campaign: str,
                     keep_output: bool, zstd_level: int, no_compress: bool):
    """
    Perform the same steps as finalize_legacy_run.py, but as a callable.
    Returns dict with status info.
    """
    params_path = run_path / "params.json"
    if not params_path.exists():
        return {"status": "skip_no_params", "run_dir": str(run_path)}

    run_id = _gen_uuid8()
    case_id = f"{run_id}__{label}"
    new_dirname = f"run_{case_id}"
    new_path = run_path.parent / new_dirname

    # 1) rewrite params.json (old -> new) (or skip if already new)
    did, msg = convert_params_file(
        params_path=params_path,
        apply=apply,
        backup_suffix=backup_suffix,
        label=label,
        campaign=campaign,
    )

    # 2) cleanup
    removed = clean_solps_run_dir(
        str(run_path),
        remove_output_dir=(not keep_output),
        dry_run=(not apply),
    )

    if not apply:
        return {
            "status": "dryrun",
            "run_dir": str(run_path),
            "would_new_dir": str(new_path),
            "rewrite_msg": msg,
            "cleanup_n": len(removed),
        }

    # 3) rename folder
    if new_path.exists():
        return {"status": "error_target_exists", "run_dir": str(run_path), "target": str(new_path)}

    run_path.rename(new_path)

    # 4) patch params.json
    new_params_path = new_path / "params.json"
    _patch_params_after_rename(new_params_path, new_case_id=case_id, new_run_dir=new_path)

    # 5) compress
    archive = None
    if not no_compress:
        archive = compress_and_remove_run_dir(str(new_path), level=zstd_level)

    return {
        "status": "ok",
        "old_dir": str(run_path),
        "new_dir": str(new_path),
        "archive": archive,
        "rewrite_msg": msg,
        "cleanup_n": len(removed),
        "case_id": case_id,
    }


def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    results = {
        "root": str(root),
        "time": datetime.now().isoformat(timespec="seconds"),
        "apply": bool(args.apply),
        "label": args.label,
        "processed": 0,
        "ok": 0,
        "skip_no_params": 0,
        "dryrun": 0,
        "errors": 0,
        "items": [],
    }

    run_dirs = sorted([p for p in root.glob("run_*") if p.is_dir()])

    if args.limit and args.limit > 0:
        run_dirs = run_dirs[: args.limit]

    for run_path in run_dirs:
        # Optional: skip if archive already exists
        if args.skip_if_archived and Path(str(run_path) + ".tar.zst").exists():
            results["items"].append({"status": "skip_already_archived", "run_dir": str(run_path)})
            results["processed"] += 1
            continue

        try:
            rec = finalize_one_dir(
                run_path,
                label=args.label,
                apply=args.apply,
                backup_suffix=args.backup_suffix,
                campaign=args.campaign,
                keep_output=args.keep_output,
                zstd_level=args.zstd_level,
                no_compress=args.no_compress,
            )
        except Exception as e:
            rec = {"status": "error_exception", "run_dir": str(run_path), "error": str(e)}

        results["items"].append(rec)
        results["processed"] += 1
        if rec["status"] == "ok":
            results["ok"] += 1
        elif rec["status"] == "skip_no_params":
            results["skip_no_params"] += 1
        elif rec["status"] == "dryrun":
            results["dryrun"] += 1
        else:
            if rec["status"].startswith("error"):
                results["errors"] += 1

        # Minimal console log
        print(f"{rec['status']}: {run_path.name}")

    # Write a report you can grep later
    report_path = root / f"finalize_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    _write_json(report_path, results)
    print(f"\nReport: {report_path}")
    print(f"Summary: processed={results['processed']} ok={results['ok']} skip_no_params={results['skip_no_params']} errors={results['errors']} apply={results['apply']}")


if __name__ == "__main__":
    main()
#python3 finalize_legacy_root.py --root "/Users/42d/ORNL Dropbox/Abdou DIaw/SOLPS DB" --label D_C_Ne --apply
