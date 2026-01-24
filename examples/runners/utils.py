import os, shutil, glob, time, subprocess, json
from tqdm import tqdm
from datetime import datetime
from pathlib import Path
import sqlite3
import json
import os
import time

def _extract_vector_from_params(meta: dict):
    puff_targets = _safe_get(meta, "inputs.gas_puffing.targets", {}) or {}
    puff_d2 = float(_safe_get(puff_targets, "D2.value", 0.0) or 0.0)
    puff_ne = float(_safe_get(puff_targets, "Ne.value", 0.0) or 0.0)

    pe = float(_safe_get(meta, "inputs.power.Pe_W", 0.0) or 0.0)
    pi = float(_safe_get(meta, "inputs.power.Pi_W", 0.0) or 0.0)
    ptot = pe + pi

    core_flux = float(_safe_get(meta, "inputs.core.particle_flux_s-1", 0.0) or 0.0)
    dna = float(_safe_get(meta, "inputs.transport.dna.value", 0.0) or 0.0)
    hci = float(_safe_get(meta, "inputs.transport.hci.value", 0.0) or 0.0)
    hce = float(_safe_get(meta, "inputs.transport.hce.value", 0.0) or 0.0)

    return puff_d2, puff_ne, ptot, core_flux, dna, hci, hce
    
def ensure_cases_sqlite(sqlite_path: str) -> None:
    """Create the cases table if it doesn't exist; add missing columns if it does."""
    os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
    conn = sqlite3.connect(sqlite_path, timeout=30)
    cur = conn.cursor()

    # Create base table if missing (includes newest columns)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id     TEXT PRIMARY KEY,
            run_dir     TEXT,
            params_path TEXT,
            machine     TEXT,
            campaign    TEXT,
            label       TEXT,
            created_ts  TEXT,
            converged   INTEGER,
            returncode  INTEGER,

            puff_d2     REAL,
            puff_ne     REAL,
            ptot_w      REAL,
            core_flux   REAL,
            dna         REAL,
            hci         REAL,
            hce         REAL
        );
    """)

    # --- migrate older DBs: add any missing columns ---
    cur.execute("PRAGMA table_info(cases);")
    existing = {row[1] for row in cur.fetchall()}  # row[1] = column name

    # Add missing columns safely
    if "hce" not in existing:
        cur.execute("ALTER TABLE cases ADD COLUMN hce REAL;")

    # (If you add more columns later, follow the same pattern here.)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_machine_campaign ON cases(machine, campaign);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_label ON cases(label);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_converged ON cases(converged);")

    conn.commit()
    conn.close()


def _safe_get(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur
    
def upsert_case_to_sqlite(sqlite_path: str, params_path: str, returncode: int,
                          max_retries: int = 15, base_sleep_s: float = 0.05) -> None:
    """
    Upsert one row into SQLite for this case.
    Retry loop makes it safe with multiple libE workers.
    """
    params_path = os.path.abspath(params_path)
    with open(params_path, "r") as f:
        meta = json.load(f)

    case_id = _safe_get(meta, "case.case_id", "") or os.path.basename(os.path.dirname(params_path)).replace("run_", "")
    run_dir = _safe_get(meta, "case.location.path", os.path.dirname(params_path)) or os.path.dirname(params_path)
    machine = _safe_get(meta, "machine", "")
    campaign = _safe_get(meta, "campaign", "")
    label = _safe_get(meta, "case.label", "")
    created_ts = _safe_get(meta, "case.created_ts", "") or _safe_get(meta, "case.created", "")
    converged = 1 if bool(_safe_get(meta, "case.status.converged", False)) else 0

    puff_d2, puff_ne, ptot_w, core_flux, dna, hci, hce  = _extract_vector_from_params(meta)

    for k in range(max_retries):
        try:
            conn = sqlite3.connect(sqlite_path, timeout=30)
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO cases
                (case_id, run_dir, params_path, machine, campaign, label, created_ts, converged, returncode,
                 puff_d2, puff_ne, ptot_w, core_flux, dna, hci, hce)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                case_id, run_dir, params_path, machine, campaign, label, created_ts,
                converged, int(returncode),
                puff_d2, puff_ne, ptot_w, core_flux, dna, hci, hce
            ))
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            # database is locked => backoff & retry
            msg = str(e).lower()
            if "locked" in msg or "busy" in msg:
                time.sleep(base_sleep_s * (2 ** min(k, 6)))
                continue
            raise
            
def looks_finished_by_runlog(run_dir: str) -> bool:
    logp = Path(run_dir) / "run.log"
    if not logp.exists():
        return False
    try:
        tail = logp.read_text(errors="ignore")[-5000:]
    except Exception:
        return False
    return ("Total cpu" in tail) and ("Total elapsed" in tail)


def done_run_dirs():
    # primary: .done.json
    dirs = set(os.path.dirname(p) for p in glob.glob(os.path.join(out_root, "run_*", ".done.json")))
    # fallback: run.log signature
    for d in glob.glob(os.path.join(out_root, "run_*")):
        if os.path.isdir(d) and looks_finished_by_runlog(d):
            dirs.add(d)
    return sorted(dirs)


def clean_solps_run_dir(run_dir: str,
                        remove_output_dir: bool = True,
                        remove_diag_dirs: bool = True,
                        remove_db_dirs: bool = True,
#                        keep_fort_i: tuple = ("fort.44.i", "fort.46.i"),
                        keep_fort_i: tuple = (),
                        dry_run: bool = False) -> list:
    """
    Delete known SOLPS junk files/dirs to reduce disk before compression.

    Returns: list of removed paths (strings)
    """
    p = Path(run_dir)
    removed = []

    def _rm(path: Path):
        if not path.exists():
            return
        removed.append(str(path))
        if dry_run:
            return
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    # --- 1) Editor backups / temp files ---
    for pat in ("*~",):
        for f in p.glob(pat):
            _rm(f)

    # --- 2) gnuplot junk ---
    for name in ("gnuplot.data", "gnuplot.data.tmp", "gnuplot.cmd"):
        _rm(p / name)

    # --- 3) Big time-step outputs (your output.0001... and output.*) ---
    for f in p.glob("output.*"):
        _rm(f)

    # --- 4) .i files (intermediate); keep specific fort.*.i if requested ---
    keep_set = set(keep_fort_i)
    for f in p.glob("*.i"):
        if f.name in keep_set:
            continue
        _rm(f)
    for f in p.glob("fort.*.i"):
        if f.name in keep_set:
            continue
        _rm(f)

    # --- 5) Common bulky files you listed ---
    for name in (
        "stra.dat", "weis.dat", "vertex_data.out",
        "b2fparam", "b2fstati", "b2ftrace", "b2ftrack", "b2fmovie",
        "b2fgmtry", "b2frates", "b2stati",
        "b2plot.ps", "b2mn.prt",
    ):
        _rm(p / name)

    # --- 6) Duplicate DB directories (usually same for every run) ---
    if remove_db_dirs:
        for d in ("AMJUEL", "AMMONX", "H2VIBR", "HYDHEL", "METHANE", "PHOTON", "SPUTER"):
            _rm(p / d)

    # --- 7) Diagnostic dirs you likely don't need later ---
    if remove_diag_dirs:
        for d in ("batch_av", "run_av", "tracing"):
            _rm(p / d)

    # --- 8) The big 'output/' directory (careful: only remove if you don't need it) ---
    if remove_output_dir:
        _rm(p / "output")

    return removed

def compress_and_remove_run_dir(run_dir: str, level: int = 19) -> str:
    """
    Create run_dir.tar.zst next to run_dir, verify it, then delete run_dir.
    Returns archive path.
    """
    run_path = Path(run_dir).resolve()
    if not run_path.is_dir():
        raise FileNotFoundError(f"run_dir not found or not a directory: {run_path}")

    archive_path = run_path.with_suffix(run_path.suffix + ".tar.zst") if run_path.suffix else Path(str(run_path) + ".tar.zst")
    # Better: keep naming consistent with your shell usage: <dir>.tar.zst
    archive_path = Path(str(run_path) + ".tar.zst")

    # If archive already exists, we can verify it and (optionally) delete the folder.
    if archive_path.exists():
        subprocess.run(["zstd", "-t", str(archive_path)], check=True)
        # If archive is OK, you may choose to remove the directory:
        # shutil.rmtree(run_path)
        return str(archive_path)

    # Build tar command: tar --sort=name -I 'zstd -19 -T0' -cvf <archive> <dir>
    # Note: tar expects archive file path, then directory path.
    cmd = [
        "tar",
        "--sort=name",
        "-I",
        f"zstd -{level} -T0",
        "-cvf",
        str(archive_path),
        str(run_path.name),
    ]

    # Run tar from parent directory so the archive doesn’t store absolute paths
    parent = run_path.parent

    # Create archive
    subprocess.run(cmd, cwd=str(parent), check=True)

    # Verify archive integrity BEFORE deleting data
    subprocess.run(["zstd", "-t", str(archive_path)], cwd=str(parent), check=True)

    # Optional: print size
    subprocess.run(["du", "-sh", str(archive_path)], cwd=str(parent), check=False)

    # Remove directory only after verification
    shutil.rmtree(run_path)

    return str(archive_path)


def default_nworkers(np_ranks: int, reserve_cores: int = 2) -> int:
    cores = os.cpu_count() or 1
    max_concurrent = max(1, (cores - reserve_cores) // max(1, np_ranks))
    # libE local: one worker can run one sim at a time
    return max_concurrent + 1  # +1 gives the generator breathing room
    
    
def watch_progress_by_donefiles(out_root, total, stop_event, poll_s=1.0,
                                do_cleanup=True,
                                cleanup_dry_run=False,
                                cleanup_remove_output=True,
                                do_compress=False,
                                zstd_level=19):
    pbar = tqdm(total=total, desc="SOLPS cases finished", dynamic_ncols=True, unit="case")
    seen = 0
    cleaned = set()

    def done_files():
        return sorted(glob.glob(os.path.join(out_root, "run_*", ".done.json")))

    while True:
        files = done_files()
        n = len(files)

        # Update progress bar
        if n > seen:
            pbar.update(n - seen)
            seen = n

        # Clean any newly finished run directories
        if do_cleanup:
            for done_path in files:
                run_dir = os.path.dirname(done_path)
                if run_dir in cleaned:
                    continue

                # extra safety: only clean if done marker exists
                if os.path.exists(done_path):
                    try:
                        removed = clean_solps_run_dir(
                            run_dir,
                            remove_output_dir=cleanup_remove_output,
                            dry_run=cleanup_dry_run,
                        )
                        cleaned.add(run_dir)
                        # Optional: write a small record
                        rec_path = os.path.join(run_dir, ".cleaned.json")
                        if not cleanup_dry_run:
                            with open(rec_path, "w") as f:
                                json.dump({"removed": removed, "time": datetime.now().isoformat()}, f, indent=2)
                    except Exception as e:
                        # Don't kill the whole watcher on cleanup failure
                        print(f"[cleanup] WARNING: failed to clean {run_dir}: {e}", flush=True)

        # ------------------------------
        # Compress successful runs (optional)
        # ------------------------------
           # ------------------------------
        # Compress successful runs (optional)
        # ------------------------------
        if do_compress:
            for done_path in files:   # reuse files already computed above
                run_dir = os.path.dirname(done_path)

                # If already compressed, skip
                if os.path.exists(run_dir + ".tar.zst"):
                    continue

                try:
                    archive = compress_and_remove_run_dir(run_dir, level=zstd_level)
                    print(f"[archive] {run_dir} -> {archive}", flush=True)
                except Exception as e:
                    print(f"[archive][WARN] failed to archive {run_dir}: {e}", flush=True)

        if seen >= total:
            break

        if stop_event.is_set():
            # final sweep before quitting
            files = done_files()
            if len(files) > seen:
                pbar.update(len(files) - seen)
            break

        time.sleep(poll_s)


    pbar.close()

def build_ensemble_dirname(machine: str, campaign: str, species_lbl: str,
                           mode: str, method: str, stamp: str) -> str:
    def clean(s: str) -> str:
        return str(s).replace(" ", "").replace("/", "-")
    return f"ens__{clean(machine)}__{clean(campaign)}__{clean(species_lbl)}__{clean(mode)}__{clean(method)}__{stamp}"


def ensure_baserun(out_root: str, baserun_src: str, mode: str = "symlink") -> str:
    baserun_src = os.path.abspath(baserun_src)
    dst = os.path.join(out_root, "baserun")

    if not os.path.isdir(baserun_src):
        raise FileNotFoundError(f"baserun source not found: {baserun_src}")

    if os.path.exists(dst):
        return dst

    if mode == "symlink":
        os.symlink(baserun_src, dst)
    elif mode == "copy":
        shutil.copytree(baserun_src, dst, dirs_exist_ok=True)
    else:
        raise ValueError("mode must be 'symlink' or 'copy'")

    return dst


def _append_status(out_root, msg):
    path = os.path.join(out_root, "status.jsonl")
    with open(path, "a") as f:
        f.write(msg + "\n")
        f.flush()

def clean_run_dir(run_dir: str) -> None:
    """Remove stale SOLPS outputs so a fresh run doesn't trip restart/append logic."""
    # Remove any *.prt files
    for prt_file in glob.glob(os.path.join(run_dir, "*.prt")):
        try:
            os.remove(prt_file)
        except FileNotFoundError:
            pass

    # Remove known SOLPS outputs (add whatever your runs generate)
    files_to_remove = [
        "b2fpardf",     # <-- your current failure
        "b2mn.prt",
        "b2fparam",
        "b2fmovie",
        "b2fstate",
        "b2ftrace",
        "b2ftrack",
        "b2time.nc",
        "b2tallies.nc",     # often appended
        "b2.transport.parameters~",  # if your editor/tool makes backups
        "run.log",
    ]

    for name in files_to_remove:
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            os.remove(path)


def _append_index(out_root: str, record: dict) -> None:
    path = os.path.join(out_root, "index.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
