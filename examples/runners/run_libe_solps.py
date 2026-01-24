#!/usr/bin/env python
#
# Author: Abdou Diaw


#######################################################################
# Sample parameters space, edits solps file and launch ensemble simulations
# Using LibEnsemble
# hard-wired: currently only edits:
## 1.b2.boundary.parameters
## 2.b2.neutrals.parameters
## 3.b2.transports.parameters
## python3 run_libe_solps.py \
#  --baserun-src /Users/42d/runs/d3d/174310_LDRD/3500_D+C+Ne/baserun \
#  --warm-start-dir /Users/42d/runs/d3d/174310_LDRD/3500_D+C+Ne/puff2.5e21_ss \
#  --solps-exe b2mn_glibc \
#  --np-ranks 40 \
#  --sim-max 4 \
#  --nworkers 2 \
#  --batch 2

#######################################################################



import os, shutil, sys, json
import numpy as np
from threading import Thread, Event
from tqdm import tqdm
from datetime import datetime
from libensemble.libE import libE
from libensemble.gen_funcs.sampling import latin_hypercube_sample
from libensemble.tools import add_unique_random_streams
import time
import glob
import subprocess
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO_ROOT)

from solpsmeta import SpeciesSpec, meta_builder, make_case_from_template, apply_edits, species_label
from sim_f_solps import sim_f
import argparse

from pathlib import Path
from utils import looks_finished_by_runlog, done_run_dirs, clean_solps_run_dir, compress_and_remove_run_dir
from utils import default_nworkers, watch_progress_by_donefiles, build_ensemble_dirname, ensure_baserun, clean_run_dir
from utils import ensure_cases_sqlite


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sim-max", type=int, default=int(os.getenv("SOLPS_SIM_MAX", "4")))
    p.add_argument("--nworkers", type=int, default=int(os.getenv("SOLPS_NWORKERS", "0")))
    p.add_argument("--batch", type=int, default=int(os.getenv("SOLPS_GEN_BATCH", "4")))
    p.add_argument("--poll", type=float, default=float(os.getenv("SOLPS_POLL_S", "1.0")))

    p.add_argument("--baserun-src", default=os.getenv("SOLPS_BASERUN_SRC"))
    p.add_argument("--warm-start-dir", default=os.getenv("SOLPS_WARM_START_DIR"))
    p.add_argument("--solps-exe", default=os.getenv("SOLPS_EXE", "b2mn_glibc"))
    p.add_argument("--np-ranks", type=int, default=int(os.getenv("SOLPS_NP_RANKS", "40")))
    p.add_argument("--dry-run", action="store_true")

    p.add_argument("--no-cleanup", action="store_true")
    p.add_argument("--cleanup-dry-run", action="store_true", default=False)
    p.add_argument("--cleanup-keep-output", action="store_true", default=False)

    p.add_argument("--no-compress", action="store_true")
    p.add_argument("--zstd-level", type=int, default=19)
    return p.parse_args()


def main():

    args = parse_args()

    do_cleanup = (not args.no_cleanup)
    do_compress = (not args.no_compress)
    
    if not args.baserun_src:
        raise ValueError("Missing --baserun-src (or SOLPS_BASERUN_SRC)")
    if not args.warm_start_dir:
        raise ValueError("Missing --warm-start-dir (or SOLPS_WARM_START_DIR)")

    baserun_src = os.path.abspath(args.baserun_src)
    warm_start_dir = os.path.abspath(args.warm_start_dir)
    if not os.path.isdir(warm_start_dir):
        raise FileNotFoundError(f"warm_start_dir not found: {warm_start_dir}")

    solps_exe = "/bin/echo" if args.dry_run else args.solps_exe
    np_ranks = args.np_ranks


    species = SpeciesSpec(
        main_ion="D",
        impurities=["C", "Ne"],
        charge_state_ranges={"D": [0, 1], "C": [0, 6], "Ne": [0, 10]},
    )

    base_meta = {
        "machine": "DIII-D",
        "campaign": "174310_LDRD",
        "authors": ["A. Diaw", "J. Lore", "J.S. Park", "S. De Pascuale"],
        "owner": "ORNL",
        "notes": "libEnsemble LHS",
    }

    mode = "ss"
    method = "lhs"
    sp_lbl = species_label(species)

#    lb = np.array([1.0e21, 1.0e19, 2.0e6, 1.0e20, 0.1, 0.1], float)
 #   ub = np.array([5.0e21, 5.0e19, 1.6e7, 7.5e20, 2.0, 2.0], float)

    lb = np.array([5.0e21, 5.0e19, 2.0e6, 7.5e20, 1.0, 1.0], float)
    ub = np.array([5.0e21, 5.0e19, 1.6e7, 7.5e20, 1.0, 1.0], float)

    sim_max = args.sim_max
    batch = args.batch
    poll_s = args.poll

    if args.nworkers == 0:
        nworkers = default_nworkers(np_ranks)
    else:
        nworkers = args.nworkers
    nworkers = max(2, min(nworkers, sim_max + 1))

    exit_criteria = {"sim_max": sim_max}

    gen_specs = {
        "gen_f": latin_hypercube_sample,
        "inputs": [],
        "persis_in": ["rand_stream"],
        "out": [("x", float, 6)],
        "user": {"gen_batch_size": batch, "lb": lb, "ub": ub},
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.join(
        HERE,
        build_ensemble_dirname(
            machine=base_meta["machine"],
            campaign=base_meta["campaign"],
            species_lbl=sp_lbl,
            mode=mode,
            method=method,
            stamp=stamp,
        ),
    )
    os.makedirs(out_root, exist_ok=True)
    ensure_baserun(out_root, baserun_src, mode="symlink")

    sqlite_path = os.path.join(out_root, "cases.sqlite")
    ensure_cases_sqlite(sqlite_path)


    sim_specs = {
        "sim_f": sim_f,
        "inputs": ["x"],
        "out": [("status", int), ("case_id", "U128"), ("run_dir", "U512")],
        "user": {
            "warm_start_dir": warm_start_dir,
            "out_root": out_root,
            "solps_exe": solps_exe,
            "np_ranks": np_ranks,
            "sqlite_path": sqlite_path,   # <--- ADD
            "species": species,
            "base_meta": {**base_meta, "mode": mode, "method": method, "species_label": sp_lbl},
        },
    }


    # watcher thread (progress + cleanup only)
    stop = Event()
    t = Thread(
        target=watch_progress_by_donefiles,
        args=(out_root, sim_max, stop),
        kwargs={
            "poll_s": poll_s,
            "do_cleanup": do_cleanup,
            "cleanup_dry_run": args.cleanup_dry_run,
            "cleanup_remove_output": (not args.cleanup_keep_output),
            "do_compress": do_compress,
            "zstd_level": args.zstd_level,
        },
        daemon=True,
    )

    t.start()

    with open(os.path.join(out_root, "ensemble_meta.json"), "w") as f:
        json.dump(
            {
                "schema": "solps-ensemble-v1",
                "created": stamp,
                "machine": base_meta["machine"],
                "campaign": base_meta["campaign"],
                "mode": mode,
                "method": method,
                "species": sp_lbl,
                "warm_start_dir": warm_start_dir,
                "baserun_src": baserun_src,
                "np_ranks_per_case": np_ranks,
                "sim_max": sim_max,
                "nworkers": nworkers,
                "gen_batch_size": batch,
            },
            f,
            indent=2,
        )

    libE_specs = {"comms": "local", "nworkers": nworkers}
    persis_info = add_unique_random_streams({}, nworkers + 1)

    try:
        H, persis_info, flag = libE(sim_specs, gen_specs, exit_criteria, persis_info, libE_specs=libE_specs)
    finally:
        stop.set()
        t.join(timeout=1)

    # Final cleanup sweep (handles missing .done.json using run.log signature)
    if do_cleanup:
        for run_dir in glob.glob(os.path.join(out_root, "run_*")):
            if not os.path.isdir(run_dir):
                continue
            done_marker = os.path.join(run_dir, ".done.json")
            if not (os.path.exists(done_marker) or looks_finished_by_runlog(run_dir)):
                continue
            if os.path.exists(os.path.join(run_dir, ".cleaned.json")):
                continue

            try:
                removed = clean_solps_run_dir(
                    run_dir,
                    remove_output_dir=(not args.cleanup_keep_output),
                    dry_run=args.cleanup_dry_run,
                )
                if not args.cleanup_dry_run:
                    with open(os.path.join(run_dir, ".cleaned.json"), "w") as f:
                        json.dump({"removed": removed, "time": datetime.now().isoformat()}, f, indent=2)
            except Exception as e:
                print(f"[cleanup] WARNING: final sweep failed for {run_dir}: {e}", flush=True)

    # Final compression sweep
    if do_compress:
        for run_dir in glob.glob(os.path.join(out_root, "run_*")):
            if not os.path.isdir(run_dir):
                continue
            done_marker = os.path.join(run_dir, ".done.json")
            if not (os.path.exists(done_marker) or looks_finished_by_runlog(run_dir)):
                continue

            archive = run_dir + ".tar.zst"
            if os.path.exists(archive):
                continue

            try:
                compress_and_remove_run_dir(run_dir, level=args.zstd_level)
                print(f"[archive] {Path(run_dir).name} -> {Path(archive).name}", flush=True)
            except Exception as e:
                print(f"[archive][WARN] failed for {run_dir}: {e}", flush=True)

    print("nworkers =", nworkers)
    print("persis_info keys =", sorted(persis_info.keys()))


if __name__ == "__main__":

    #python3 run_libe_solps.py \
    #  --baserun-src /Users/42d/runs/d3d/174310_LDRD/3500_D+C+Ne/baserun \
    #  --warm-start-dir /Users/42d/runs/d3d/174310_LDRD/3500_D+C+Ne/puff2.5e21_ss \
    #  --dry-run \
    #  --sim-max 4 --nworkers 2 --batch 2



    main()


#
