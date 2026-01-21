import os, json, shutil
from typing import Dict, Any, List

from modify_solps_files import (
    _set_userflux_value,
    _set_psol_value,
    _set_conpar_density,
    _set_transport_values,
    set_puff_by_gpfc,
    infer_transport_slots
)

def build_case_id(tag_parts: List[str]) -> str:
    return "_".join(tag_parts)


def apply_edits(run_dir: str, spec: Dict[str, Any]) -> None:
    """
    spec is metadata_v2 dict. We edit files using values from spec["inputs"].
    """
    inputs = spec["inputs"]
    
    # time_dependence

    td = inputs.get("time_dependence", {"mode": "steady_state"})
    mode = td.get("mode", "steady_state")
    
    if mode != "steady_state":
            raise NotImplementedError(
                f"apply_edits currently supports steady_state only. Got time_dependence.mode='{mode}'."
            )



    # --- neutrals puffing: multiple targets with their own indices ---
    neut_path = os.path.join(run_dir, "b2.neutrals.parameters")
    with open(neut_path, "r") as f:
        neut = f.read()

    for tgt_name, tgt in inputs["gas_puffing"]["targets"].items():
        val = float(tgt["value"])

        if "gpfc" in tgt:
            neut = set_puff_by_gpfc(neut, tgt["gpfc"], val)
        elif "userfluxparm_index" in tgt:
            neut = _set_userflux_value(neut, val, index=int(tgt["userfluxparm_index"]))
        else:
            raise KeyError(f"Target {tgt_name} needs either 'gpfc' or 'userfluxparm_index'")

    with open(neut_path, "w") as f:
        f.write(neut)

    # --- boundary ---
    bnd_path = os.path.join(run_dir, "b2.boundary.parameters")
    with open(bnd_path, "r") as f:
        bnd = f.read()

    bnd = _set_psol_value(bnd, "enepar", inputs["power"]["Pe_W"])
    bnd = _set_psol_value(bnd, "enipar", inputs["power"]["Pi_W"])
    bnd = _set_conpar_density(bnd, inputs["core"]["particle_flux_s-1"])

    with open(bnd_path, "w") as f:
        f.write(bnd)

    # --- transport ---
    tr_path = os.path.join(run_dir, "b2.transport.parameters")
    with open(tr_path, "r") as f:
        tr = f.read()

    nspecies_slots = infer_transport_slots(tr, fallback=20)
    
    dna = inputs["transport"]["dna"]
    hci = inputs["transport"]["hci"]
    hce = inputs["transport"]["hce"]

    # Convert per_species dict -> a single representative value if your file expects N*value
#    dna_val = float(list(dna["values"].values())[0]) if dna["type"] == "per_species" else float(dna["value"])
#    hci_val = float(list(hci["values"].values())[0]) if hci["type"] == "per_species" else float(hci["value"])
    dna_val = float(dna["value"]) if dna["type"] == "global" else float(list(dna["values"].values())[0])
    hci_val = float(hci["value"]) if hci["type"] == "global" else float(list(hci["values"].values())[0])
    hce_val = float(hce["value"]) if hce["type"] == "global" else float(list(hce["values"].values())[0])

    tr = _set_transport_values(tr, {"parm_dna": dna_val, "parm_hci": hci_val, "parm_hce": hce_val}, nspecies_slots)

    with open(tr_path, "w") as f:
        f.write(tr)


def make_case_from_template(
    warm_start_dir: str,
    out_root: str,
    case_id: str,
) -> str:
    run_dir = os.path.join(out_root, f"run_{case_id}")
    os.makedirs(run_dir, exist_ok=True)

    for item in os.listdir(warm_start_dir):
        src = os.path.join(warm_start_dir, item)
        dst = os.path.join(run_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    return run_dir
    
