# sim_f_solps.py
import os, json, subprocess, uuid
import numpy as np
import uuid
from datetime import datetime
from solpsmeta import SpeciesSpec, meta_builder, make_case_from_template, apply_edits, _coerce_species, _species_label
import time
import glob
from utils import _append_status, _append_index, clean_run_dir
from utils import upsert_case_to_sqlite


    
def sim_f(H, persis_info, sim_specs, libE_info):
    """
    H: structured array of inputs from libEnsemble (one or more points)
    Returns H_o: structured array of outputs (status, run_dir, case_id)
    """

    # Unpack user settings
    user = sim_specs["user"]
    warm_start_dir = user["warm_start_dir"]
    out_root = user["out_root"]
    solps_exe = user["solps_exe"]
    np_ranks = int(user.get("np_ranks", 1))
    sqlite_path = user.get("sqlite_path", None)
    base_meta = user["base_meta"]
    species = user["species"]

    H_o = np.zeros(len(H), dtype=sim_specs["out"])

    for i, row in enumerate(H):
        # Map libE variables -> physical values
         # Expect vector order: puff_D2, puff_Ne, P_W, core_flux, dna, hci
        xv = row["x"]
        puff_D2, puff_Ne, P_W, core_flux, dna, hci = map(float, xv)

        Pe_W = 0.5 * P_W
        Pi_W = 0.5 * P_W

        x = {
            "puff_D2": puff_D2,
            "puff_Ne": puff_Ne,
            "P_W": P_W,
            "Pe_W": Pe_W,
            "Pi_W": Pi_W,
            "core_flux": core_flux,
            "dna": dna,
            "hci": hci,
        }

        run_id = uuid.uuid4().hex[:8]
        label = _species_label(species)
        case_id = f"{run_id}__{label}"     # pass as the 3rd arg
        run_dir = make_case_from_template(warm_start_dir, out_root, case_id)

        start_msg = json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": "start",
            "case_id": case_id,
            "run_dir": run_dir,
        })
        _append_status(out_root, start_msg)

        puff_targets = {
            "D2": {"value": x["puff_D2"], "gpfc": [2, 0, 0]},
            "Ne": {"value": x["puff_Ne"], "gpfc": [0, 0, 1]},
        }

        transport = {
            "units": "SI",
            "slots": 20,  # important so parm_dna/parm_hci become 20*...
            "dna": {"type": "global", "value": x["dna"]},
            "hci": {"type": "global", "value": x["hci"]},
            "hce": {"type": "global", "value": x["hci"]},
        }

        species0 = _coerce_species(species)
        spec = meta_builder(
            machine=base_meta["machine"],
            time_dependence={"mode": "steady_state"},
            case_id=case_id,
            campaign=base_meta["campaign"],
            run_dir=run_dir,
            authors=base_meta["authors"],
            owner=base_meta["owner"],
            species=species0,
            puff_targets=puff_targets,
            Pe_W=x["Pe_W"],
            Pi_W=x["Pi_W"],
            core_flux=x["core_flux"],
            transport=transport,
            notes=base_meta.get("notes", ""),
            converged=False,
        )

        spec["case"]["run_id"] = run_id
        spec["case"]["label"] = label
        spec["case"]["created_ts"] = datetime.now().isoformat(timespec="seconds")

        with open(os.path.join(run_dir, "params.json"), "w") as f:
            json.dump(spec, f, indent=2)


        _append_index(out_root, {
            "run_id": run_id,
            "label": label,
            "case_dir": run_dir,
            "machine": spec["machine"],
            "created": spec["case"]["created_ts"],
            "authors": spec["case"]["authors"],
            "status": "created",
        })

        apply_edits(run_dir, spec)

        clean_run_dir(run_dir)

        launcher = user.get("launcher", ["mpirun", "-np"])
        cmd = launcher + [str(np_ranks), solps_exe]
        
        log_path = os.path.join(run_dir, "run.log")   # <-- ADD THIS

        with open(log_path, "w") as logfile:
            proc = subprocess.Popen(
                cmd,
                cwd=run_dir,
                stdout=logfile,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )
        ret = proc.wait()
        
        done_path = os.path.join(run_dir, ".done.json")
        with open(done_path, "w") as f:
            json.dump(
            {"case_id": case_id, "t_end": time.time(), "status": int(ret)},
            f,
            )

        # Update converged flag in params.json (truth lives in the run_dir)
        spec["case"]["status"]["converged"] = (ret == 0)
        with open(os.path.join(run_dir, "params.json"), "w") as f:
            json.dump(spec, f, indent=2)

        # Append to SQLite index (optional)
        if sqlite_path:
            try:
                upsert_case_to_sqlite(sqlite_path, os.path.join(run_dir, "params.json"), returncode=ret)
            except Exception as e:
                # Don't fail the whole simulation because the index write had a hiccup
                warn_msg = json.dumps({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "event": "index_warn",
                    "case_id": case_id,
                    "run_dir": run_dir,
                    "error": str(e),
                })
                _append_status(out_root, warn_msg)


        end_msg = json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": "end",
            "case_id": case_id,
            "run_dir": run_dir,
            "returncode": ret,
        })
        _append_status(out_root, end_msg)

        H_o[i]["status"] = int(ret)
        H_o[i]["case_id"] = case_id
        H_o[i]["run_dir"] = run_dir


    return H_o, persis_info

