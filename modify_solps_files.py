
import re

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
        print(f"⚠️ '{varname}(1,1)=' not found.")
    else:
        print(f"✅ Updated {varname}(1,1) to {float(new_val):.4E}")
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
            print(f"⚠️ Parameter '{key}' not found in transport file.")
        else:
            print(f"✅ Updated '{key}' to {replacement_value}")

    return content


def _set_conpar_density(str_text, new_val):
    """
    Updates the second value in the conpar(0,1,1)= line with new_val,
    preserving the rest of the line.
    """
    pattern = r"(conpar\(0,1,1\)=\s*[\d.Ee+-]+,\s*)([\d.Ee+-]+)(,?)"
    replacement = r"\g<1>{:<10.4E}\g<3>".format(float(new_val))
    return re.sub(pattern, replacement, str_text)


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

def _format_userflux(prefix: str, vals: list) -> str:
    # Keep it one line (simple) — you can wrap later if you want.
    return prefix + ", ".join(vals) + "\n"

def set_puff_by_gpfc(text: str, target_gpfc: list, value: float) -> str:
    """
    Find stream index i where gpfc(1,i) == target_gpfc (e.g. [2,0,0])
    and set userfluxparm(1,1)[i] to value.
    """
    nstrai = _read_nstrai(text)
    gpfc_map = _parse_gpfc_map(text)

    matches = [i for i, tri in gpfc_map.items() if tri == target_gpfc]
    if len(matches) != 1:
        raise ValueError(f"Expected 1 gpfc match for {target_gpfc}, found {matches}")

    idx = matches[0]  # 1-based stream index

    prefix, block, pat = _get_userflux_block(text)
    vals = _parse_float_list(block)

    # Ensure list length matches nstrai
    if len(vals) < nstrai:
        vals = vals + ["0.00"] * (nstrai - len(vals))
    elif len(vals) > nstrai:
        vals = vals[:nstrai]

    vals[idx - 1] = "{:<10.4E}".format(float(value)).strip()

    new_block = _format_userflux(prefix, vals)
    return pat.sub(new_block, text, count=1)
