#!/usr/bin/env python3
import argparse, json, os, re, sqlite3, subprocess, time
from pathlib import Path

from utils import ensure_cases_sqlite, _safe_get  # reuse yours

ARCH_RE = re.compile(r"run_[0-9a-f]{8}__.+\.tar\.zst$")

def read_params_from_tar_zst(archive_path: str) -> dict:
    """
    Stream-extract params.json from a .tar.zst without writing to disk.
    Assumes archive contains something like: run_xxx__LABEL/params.json
    """
    archive_path = os.path.abspath(archive_path)

    # 1) list tar members (streaming)
    p_list = subprocess.run(
        ["bash", "-lc", f"zstd -dc {shq(archive_path)} | tar -tf -"],
        check=True, capture_output=True, text=True
    )
    members = p_list.stdout.splitlines()

    # find params.json member
    cand = None
    for m in members:
        # common: run_xxx__LABEL/params.json
        if m.endswith("/params.json") or m == "params.json":
            cand = m
            break
    if not cand:
        raise FileNotFoundError(f"params.json not found inside {archive_path}")

    # 2) extract that member to stdout
    p_x = subprocess.run(
        ["bash", "-lc", f"zstd -dc {shq(archive_path)} | tar -xOf - {shq(cand)}"],
        check=True, capture_output=True, text=True
    )
    return json.loads(p_x.stdout)

def shq(s: str) -> str:
    # minimal shell quoting
    return "'" + s.replace("'", "'\"'\"'") + "'"

def extract_vector(meta: dict):
    puff_targets = _safe_get(meta, "inputs.gas_puffing.targets", {}) or {}
    puff_d2 = float(_safe_get(puff_targets, "D2.value", 0.0) or 0.0)
    puff_ne = float(_safe_get(puff_targets, "Ne.value", 0.0) or 0.0)

    pe = float(_safe_get(meta, "inputs.power.Pe_W", 0.0) or 0.0)
    pi = float(_safe_get(meta, "inputs.power.Pi_W", 0.0) or 0.0)
    ptot = pe + pi

    core_density = float(_safe_get(meta, "inputs.core.density_m-3", 0.0) or 0.0)
    dna = float(_safe_get(meta, "inputs.transport.dna.value", 0.0) or 0.0)
    hci = float(_safe_get(meta, "inputs.transport.hci.value", 0.0) or 0.0)
    hce = float(_safe_get(meta, "inputs.transport.hce.value", 0.0) or 0.0)
    return puff_d2, puff_ne, ptot, core_density, dna, hci, hce

def upsert_archive_row(sqlite_path: str, archive_path: str, meta: dict, returncode: int = 0):
    case_id = _safe_get(meta, "case.case_id", "") or ""
    machine = _safe_get(meta, "machine", "") or ""
    campaign = _safe_get(meta, "campaign", "") or ""
    label = _safe_get(meta, "case.label", "") or ""
    created_ts = _safe_get(meta, "case.created_ts", "") or _safe_get(meta, "case.created", "") or ""
    converged = 1 if bool(_safe_get(meta, "case.status.converged", False)) else 0

    puff_d2, puff_ne, ptot_w, core_density, dna, hci, hce = extract_vector(meta)

    conn = sqlite3.connect(sqlite_path, timeout=30)
    cur = conn.cursor()

    # Ensure archive_path column exists (migration-safe)
    cur.execute("PRAGMA table_info(cases);")
    cols = {r[1] for r in cur.fetchall()}
    if "archive_path" not in cols:
        cur.execute("ALTER TABLE cases ADD COLUMN archive_path TEXT;")

    cur.execute("""
        INSERT OR REPLACE INTO cases
        (case_id, run_dir, params_path, machine, campaign, label, created_ts, converged, returncode,
         puff_d2, puff_ne, ptot_w, core_density, dna, hci, hce, archive_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        case_id,
        "",              # run_dir not present anymore (archive-only)
        "",              # params_path not present anymore (archive-only)
        machine, campaign, label, created_ts, converged, int(returncode),
        puff_d2, puff_ne, ptot_w, core_density, dna, hci, hce,
        os.path.abspath(archive_path),
    ))
    conn.commit()
    conn.close()

def iter_archives(root: Path):
    # recurse a bit: your tarballs might be inside ens__... folders
    for p in root.rglob("run_*.tar.zst"):
        yield p

def parse_args():
    ap = argparse.ArgumentParser(description="Index run_*.tar.zst archives into cases.sqlite by streaming params.json out of tar.zst.")
    ap.add_argument("--root", required=True, help="Root folder to scan (e.g. SOLPS DB or an ens__ folder)")
    ap.add_argument("--sqlite", required=True, help="cases.sqlite path to write/update")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N archives (0 = all)")
    ap.add_argument("--skip-if-present", action="store_true", help="Skip if archive_path already in sqlite")
    return ap.parse_args()

def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    sqlite_path = os.path.abspath(args.sqlite)

    ensure_cases_sqlite(sqlite_path)

    # preload archive_path set if skipping
    seen_archives = set()
    if args.skip_if_present and os.path.exists(sqlite_path):
        conn = sqlite3.connect(sqlite_path, timeout=30)
        cur = conn.cursor()
        try:
            cur.execute("SELECT archive_path FROM cases WHERE archive_path IS NOT NULL;")
            seen_archives = {r[0] for r in cur.fetchall() if r and r[0]}
        except sqlite3.OperationalError:
            pass
        conn.close()

    n = 0
    for arch in iter_archives(root):
        if args.limit and n >= args.limit:
            break
        apath = str(arch.resolve())
        if args.skip_if_present and apath in seen_archives:
            print(f"skip_present: {arch.name}")
            continue

        try:
            meta = read_params_from_tar_zst(apath)
            upsert_archive_row(sqlite_path, apath, meta)
            print(f"ok: {arch.name}")
            n += 1
        except Exception as e:
            print(f"FAIL: {arch} :: {e}")

    print(f"\nDone. Indexed {n} archives into {sqlite_path}")

if __name__ == "__main__":
    main()

