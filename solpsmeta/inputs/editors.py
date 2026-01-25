import re
import os, json, shutil
from typing import Dict, Any, List

    
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
    bnd = _set_conpar_density(bnd, inputs["core"]["density_m-3"])

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
    dna_val = float(dna["value"]) if dna["type"] == "global" else float(list(dna["values"].values())[0])
    hci_val = float(hci["value"]) if hci["type"] == "global" else float(list(hci["values"].values())[0])
    hce_val = float(hce["value"]) if hce["type"] == "global" else float(list(hce["values"].values())[0])

    tr = _set_transport_values(tr, {"parm_dna": dna_val, "parm_hci": hci_val, "parm_hce": hce_val}, nspecies_slots)

    with open(tr_path, "w") as f:
        f.write(tr)


def infer_transport_slots(content: str, fallback: int = 20) -> int:
    # Try to infer from any existing repeated parm_* line
    m = re.search(r"parm_(?:dpa|vla|vsa)\s*=\s*(\d+)\*", content)
    if m:
        return int(m.group(1))
    return fallback


def _sanitize_val(val, scale=1.0):
    norm = val / scale
    return f"{norm:.3f}".replace(".", "p")

def _set_userflux_value(str_text, new_val, index=6):
    """
    Updates the value at a specific index (1-based) in the userfluxparm(1,1)= line
    in b2.neutrals.parameters. Preserves the other values.
    """
    pattern = r"(userfluxparm\(1,1\)=)(.*)"
    match = re.search(pattern, str_text)
    
    if not match:
        raise ValueError("userfluxparm(1,1)= line not found")


    prefix, values_str = match.groups()
    values = [v.strip() for v in values_str.strip().split(',') if v.strip()]


    if index < 1 or index > len(values):
        raise IndexError("Index out of range for userfluxparm values")


    values[index - 1] = "{:<10.4E}".format(float(new_val))
    new_line = prefix + ' ' + ', '.join(values)
    
    return re.sub(pattern, new_line, str_text)


def _set_psol_value(str_text, varname, new_val):
    """
    Replace the FIRST numeric value on the line starting with:
      <varname>(1,1)=<number>,...
    Example varname: 'enepar', 'enipar', 'eniepar'
    """
    varname = varname.strip()
    # match: varname(1,1)= <number> , rest-of-line
    pattern = rf"({re.escape(varname)}\(1,1\)=)\s*[\d.Ee+-]+(,.*)"
    replacement = rf"\1 {float(new_val):<10.4E}\2"
    new_text, n = re.subn(pattern, replacement, str_text, count=1)
    if n == 0:
        raise ValueError(f"'{varname}(1,1)=' not found in file; cannot update.")

    return new_text


def _set_transport_values(content, params, nspecies):
    nspecies = int(nspecies)  # enforce integer
    
    # Define parameters that require repetition factor
    repeated_params = {'parm_dna', 'parm_hci'}

    for key, val in params.items():

        # Determine replacement format
        if key in repeated_params:
            replacement_value = f'{nspecies}*{val:.6e}'   # <--- changed here
        else:
            replacement_value = f'{val:.6e}'

        # Match: key = (optional "N*") value
        pattern = rf'({re.escape(key)}\s*=\s*)(\d+\*\s*)?[\d\.eE\+\-]+'

        # Substitute
        content, count = re.subn(pattern, rf'\g<1>{replacement_value}', content)

        if count == 0:
            raise ValueError(f"'{key}=' not found in file; cannot update.")
    return content


def _set_conpar_density(str_text, new_val):
    """
    Update the *second* value in: conpar(0,1,1)= <a>, <b>
    """
    pattern = r"(conpar\(0,1,1\)\s*=\s*[\d.Ee+\-]+\s*,\s*)([\d.Ee+\-]+)"
    replacement = r"\g<1>{:<10.4E}".format(float(new_val))

    new_text, n = re.subn(pattern, replacement, str_text, count=1)
    if n == 0:
        raise ValueError(f"'core_flux(1,1)=' not found in file; cannot update.")
    return new_text

def _read_nstrai(text: str) -> int:
    m = re.search(r"\bnstrai\s*=\s*(\d+)\s*,", text, re.IGNORECASE)
    if not m:
        raise ValueError("Could not find nstrai= in b2.neutrals.parameters")
    return int(m.group(1))

def _parse_gpfc_map(text: str) -> dict:
    """
    Returns {i: [a,b,c]} for lines like gpfc(1,16)= 2.00, 0.00, 0.00,
    """
    gpfc = {}
    for m in re.finditer(r"gpfc\(1,(\d+)\)\s*=\s*([^/\n]+)", text, re.IGNORECASE):
        i = int(m.group(1))
        vals = [v.strip() for v in m.group(2).split(",") if v.strip()]
        # keep only first 3 numbers
        triple = [int(float(vals[0])), int(float(vals[1])), int(float(vals[2]))]
        gpfc[i] = triple
    return gpfc

def _get_userflux_block(text: str):
    """
    Grab userfluxparm(1,1)= ... possibly spanning multiple lines,
    stopping before the next namelist assignment or '/'.
    """
    pat = re.compile(
        r"(userfluxparm\(1,1\)\s*=\s*)(.*?)(?=\n\s*[A-Za-z_]+\w*\s*\(|\n\s*[A-Za-z_]+\w*\s*=|\n\s*/)",
        re.IGNORECASE | re.DOTALL
    )
    m = pat.search(text)
    if not m:
        raise ValueError("userfluxparm(1,1)= block not found")
    return m.group(1), m.group(2), pat

def _parse_float_list(block: str):
    # Remove newlines and split on commas
    raw = block.replace("\n", " ")
    vals = [v.strip() for v in raw.split(",") if v.strip()]
    return vals  # keep as strings initially

_NUM = re.compile(r"""
    (?P<num>
        [-+]?(
            (?:\d+\.\d*)|(?:\d*\.\d+)|(?:\d+)
        )
        (?:[Ee][-+]?\d+)?
    )
""", re.VERBOSE)

def _infer_delim_between(block: str) -> str:
    """
    Return the exact text between numbers, excluding the numbers themselves.
    For your files this should become something like: "    ,  "
    """
    ms = list(_NUM.finditer(block))
    if len(ms) >= 2:
        return block[ms[0].end("num"):ms[1].start("num")]
    return "    ,  "

def _ensure_trailing_comma(block: str) -> str:
    # Keep trailing whitespace/newline
    m = re.search(r"\s*\Z", block)
    endws = m.group(0) if m else ""
    core = block[:len(block) - len(endws)]
    if not core.rstrip().endswith(","):
        core = core.rstrip() + ","
    return core + endws

def _pad_userflux_block_to_nstrai(block: str, nstrai: int, pad_token: str = "0.00") -> str:
    ms = list(_NUM.finditer(block))
    if len(ms) >= nstrai:
        return _ensure_trailing_comma(block)

    delim = _infer_delim_between(block)

    # strip end whitespace, strip ONE trailing comma if present (we'll add it back once)
    m = re.search(r"\s*\Z", block)
    endws = m.group(0) if m else ""
    core = block[:len(block) - len(endws)].rstrip()

    if core.endswith(","):
        core = core[:-1].rstrip()

    need = nstrai - len(ms)

    # Append values using *exactly* the between-number delimiter (which already contains the comma)
    for _ in range(need):
        core += delim + pad_token

    # Add exactly one trailing comma at end
    core += ","
    return core + endws

def _pad_userflux_block_to_minlen(block: str, minlen: int, pad_token: str = "0.00") -> str:
    """Pad only if needed to reach minlen numbers. Do NOT pad to nstrai."""
    nums = list(_NUM.finditer(block))
    if len(nums) >= minlen:
        return _ensure_trailing_comma(block)

    delim = _infer_delim_between(block)

    m = re.search(r"\s*\Z", block)
    endws = m.group(0) if m else ""
    core = block[:len(block) - len(endws)].rstrip()

    if core.endswith(","):
        core = core[:-1].rstrip()

    need = minlen - len(nums)
    for _ in range(need):
        core += delim + pad_token

    core += ","
    return core + endws

def set_puff_by_gpfc(text: str, target_gpfc: list, value: float) -> str:
    nstrai = _read_nstrai(text)
    gpfc_map = _parse_gpfc_map(text)

    matches = [i for i, tri in gpfc_map.items() if tri == target_gpfc]
    if len(matches) != 1:
        raise ValueError(f"Expected 1 gpfc match for {target_gpfc}, found {matches}")
    idx = matches[0]  # 1-based

    # Optional sanity check (doesn't force padding)
    if idx > nstrai:
        raise ValueError(f"gpfc index {idx} exceeds nstrai={nstrai}")

    prefix, block, pat = _get_userflux_block(text)

    # Only pad enough to safely edit idx (NOT to nstrai)
    block = _pad_userflux_block_to_minlen(block, idx, pad_token="0.00")

    nums = list(_NUM.finditer(block))
    if len(nums) < idx:
        raise ValueError(f"Padding failed: have {len(nums)} numbers, need at least {idx}")

    new_token = f"{float(value):.3E}"  # 5.000E+21 style

    m = nums[idx - 1]
    a, b = m.span("num")
    new_block = block[:a] + new_token + block[b:]

    # Keep exact original formatting, just swap the number
    return pat.sub(prefix + new_block, text, count=1)
