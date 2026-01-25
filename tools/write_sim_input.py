import re
import os
import json
import shutil

"""
This file is part of the suite of scripts to use LibEnsemble on top of SOLPS-ITER
simulations. It provides functions to modify some parameters in a SOLPS-ITER
input file.
"""

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
 
def _set_psol_value(str_text, new_val):
    """
    Replaces the first value of the enepar(1,1), enipar(1,1), or eniepar(1,1) line with new_val,
    preserving the rest of the line.
    """
    pattern = r"(en(?:i(?:e)?|e)par\(1,1\)=)\s*[\d.Ee+-]+(,.*)"
    replacement = r"\1 {:<10.4E}\2".format(float(new_val))
    return re.sub(pattern, replacement, str_text)


def _set_conpar_density(str_text, new_val):
    """
    Updates the second value in the conpar(0,1,1)= line with new_val,
    preserving the rest of the line.
    """
    pattern = r"(conpar\(0,1,1\)=\s*[\d.Ee+-]+,\s*)([\d.Ee+-]+)(,?)"
    replacement = r"\g<1>{:<10.4E}\g<3>".format(float(new_val))
    return re.sub(pattern, replacement, str_text)

def _set_transport_values(str_text, new_vals):
    """
    Updates specified transport parameters in the b2.transport.parameters file.
    new_vals should be a dict with keys like 'parm_dna', 'parm_hci', 'parm_hce'.
    - For entries with 2*value (like parm_dna=2*0.3), only value is updated, not the "2*".
    """
    for key, val in new_vals.items():
        if key in ['parm_dna', 'parm_hci']:  # keep '2*' prefix
            pattern = rf"({key}\s*=\s*)2\*[\d.Ee+-]+"
            replacement = rf"\1 2*{val}"
        else:  # no '2*'
            pattern = rf"({key}\s*=\s*)[\d.Ee+-]+"
            replacement = rf"\1 {val}"

        str_text = re.sub(pattern, replacement, str_text)

    return str_text
    
def _sanitize(val):
    """Format and clean individual parameter values for folder names"""
    return f"{val:.2e}".replace(".", "").replace("+", "").replace("-", "m")

def _sanitize(val):
    return f"{val:.8f}".replace(".", "p").replace("-", "m")

def _sanitize(val):
    return f"{val:.3e}".replace(".", "").replace("+", "").replace("-", "m")

def _sanitize_val(val, scale=1.0):
    """Normalize, round, and format to a folder-safe string with 3 decimal places"""
    norm = val / scale
    return f"{norm:.5f}".replace(".", "p").replace("-", "m")


def write_sim_input(input_files, x_values, shared_source="/home/cloud/runs_solps/d3d_ldrd/shared"):
    """
    Modifies input files based on x_values and writes them to the current directory.
    Also copies additional required files/folders from a shared source directory.
    """

    # Optional: generate and store a case ID tag (but don't create a folder)
    tag = "_".join([
        _sanitize_val(x_values["gas_puff"], 1e21),
        _sanitize_val(x_values["Pe"], 1e6),
        _sanitize_val(x_values["core_flux"], 1e20),
        _sanitize_val(x_values["dna"]),
        _sanitize_val(x_values["hci"]),
    ])
    x_values["case_id"] = tag

    # STEP 1: Copy everything from shared folder EXCEPT files that will be overwritten
    skip_files = {"b2.neutrals.parameters", "b2.boundary.parameters", "b2.transport.parameters"}

    for item in os.listdir(shared_source):
        s_path = os.path.join(shared_source, item)
        d_path = os.path.join(os.getcwd(), item)

        if os.path.lexists(d_path):
            if os.path.islink(d_path) or os.path.isfile(d_path):
                os.unlink(d_path)
            elif os.path.isdir(d_path):
                shutil.rmtree(d_path)

        if os.path.isfile(s_path):
            if item not in skip_files:
                shutil.copy2(s_path, d_path)
        elif os.path.isdir(s_path):
            shutil.copytree(s_path, d_path)
        elif os.path.islink(s_path):
            target = os.readlink(s_path)
            os.symlink(target, d_path)

    # STEP 2: Modify and save parameter files directly into current directory
    for file_name, params in input_files.items():
        with open(os.path.join(shared_source, file_name), 'r') as f:
            content = f.read()

        if file_name == "b2.neutrals.parameters" and 'gas_puff' in params:
            content = _set_userflux_value(content, x_values['gas_puff'], index=params.get('index', 6))
        elif file_name == "b2.boundary.parameters":
            if 'Pe' in params:
                content = _set_psol_value(content, x_values['Pe'])
            if 'core_flux' in params:
                content = _set_conpar_density(content, x_values['core_flux'])
        elif file_name == "b2.transport.parameters":
            content = _set_transport_values(content, {
                'parm_dna': x_values.get('dna', x_values['hce']),
                'parm_hci': x_values.get('hci', x_values['hce']),
                'parm_hce': x_values.get('hce', x_values['hci']),
            })

        with open(file_name, 'w') as f:
            f.write(content)

    # STEP 3: Save metadata
    with open("params.json", 'w') as f:
        json.dump(x_values, f, indent=2)

    return os.getcwd()  # just return current folder path

