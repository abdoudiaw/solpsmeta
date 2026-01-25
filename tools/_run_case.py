import os
import re
import time
import numpy as np
import pprint
import subprocess
from mystic.tools import random_state
from datetime import datetime
import numpy as np
import shutil
import netCDF4 as nc
import json
import glob
import re
from scipy.stats import qmc
from concurrent.futures import ProcessPoolExecutor, as_completed

# Generate date string
today_date = datetime.today().strftime('%Y-%m-%d')

from solps_iter_simf import objective as model

# create model
cost4 = lambda x: model(x)

def lhs_samples(lb, ub, npts=100):
    dim = len(lb)
    sampler = qmc.LatinHypercube(d=dim)
    sample = sampler.random(n=npts)  # shape (npts, dim)
    return qmc.scale(sample, lb, ub)
    
    
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
    
def _set_psol_value(str_text, new_val):
    """
    Replaces the first value of the enepar(1,1), enipar(1,1), or eniepar(1,1) line with new_val,
    preserving the rest of the line.
    """
    pattern = r"(en(?:i(?:e)?|e)par\(1,1\)=)\s*[\d.Ee+-]+(,.*)"
    replacement = r"\1 {:<10.4E}\2".format(float(new_val))
    return re.sub(pattern, replacement, str_text)

def _set_transport_values(content, params):
    # Define parameters that require a repetition factor
    repeated_params = {'parm_dna', 'parm_hci'}

    for key, val in params.items():
        # Determine the appropriate format based on the parameter
        if key in repeated_params:
            replacement_value = f'2*{val:.6e}'
        else:
            replacement_value = f'{val:.6e}'

        # Construct the regex pattern to match the parameter assignment
        pattern = rf'({key}\s*=\s*)(\d+\*\s*)?[\d\.eE\+\-]+'

        # Perform the substitution
        content, count = re.subn(pattern, rf'\g<1>{replacement_value}', content)

        # Provide feedback on the substitution
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

def decode_tag(tag):
    return [float(x.replace('p', '.')) for x in tag.split('_')[1:]]

def get_closest_folder(tag, dropbox_dir):
    tag_vec = np.array(decode_tag(tag))
    closest = None
    closest_dist = float('inf')

    for folder in os.listdir(dropbox_dir):
        if folder.startswith("run_"):
            try:
                folder_vec = np.array(decode_tag(folder))
                dist = np.linalg.norm(tag_vec - folder_vec)
                if dist < closest_dist:
                    closest = folder
                    closest_dist = dist
            except Exception as e:
                print(f"Skipping folder {folder}: {e}")
    return closest


def objective_(x):
    print("calling objective with params x", x)
    print(x[0], x[2])

    original_wd = os.getcwd()
    
    # Generate unique run directory
    tag = "_".join([
        _sanitize_val(x[0], 1),
        _sanitize_val(x[1], 1),
        _sanitize_val(x[2], 1),
        _sanitize_val(x[3]),
        _sanitize_val(x[4]),
    ])
    
    # Check if case was already run
    record_file = "evaluated_cases.csv"
    if os.path.exists(record_file):
        df = pd.read_csv(record_file)
        if tag in df["case_id"].values:
            print(f"⚠️ Case {tag} already evaluated. Skipping.")
            return None
            
    run_dir = os.path.join(os.getcwd(), f"run_{tag}")
    os.makedirs(run_dir, exist_ok=True)


   # Dropbox folder path
    dropbox_dir = "/home/cloud/runs_solps/d3d_ldrd/sampler/db"
    nearest = get_closest_folder(tag, dropbox_dir)
    print(f"Closest folder to {tag} is: {nearest}")


    # Copy everything from shared
    shared = "../shared"
    for item in os.listdir(shared):
        src = os.path.join(shared, item)
        dst = os.path.join(run_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif os.path.isfile(src):
            shutil.copy2(src, dst)

    # Modify parameter files
    input_files = {
        "b2.neutrals.parameters": {"gas_puff": True, "index": 6},
        "b2.boundary.parameters": {"Pe": True, "Pi": True, "core_flux": True},
        "b2.transport.parameters": {"dna": True, "hci": True, "hce": True},
    }

    # Denormalization factors
    
    def denormalize(x, factors):
        return [xi * fi for xi, fi in zip(x, factors)]
    
    factors = [1e21, 1e6, 1e20, 1, 1]
    x_denorm = denormalize(x, factors)

    x_values = {
        "gas_puff": x_denorm[0],
        "Pe":       x_denorm[1],
        "Pi":       x_denorm[1],
        "core_flux": x_denorm[2],
        "dna":      x_denorm[3],
        "hci":      x_denorm[4],
        "hce":      x_denorm[4],
        "case_id":  tag,
    }

    for file_name, params in input_files.items():
        path = os.path.join(run_dir, file_name)
        
        with open(path, 'r') as f:
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

        with open(path, 'w') as f:
            f.write(content)

    # Save metadata
    params = {
    "solps-iter-params": [
        {
            "machine": "DIIID",
            "case_id": tag,
            "gas_puff": x_values["gas_puff"],
            "Pe": x_values["Pe"],
            "Pi": x_values["Pi"],
            "core_flux": x_values["core_flux"],
            "dna": x_values["dna"],
            "hci": x_values["hci"],
            "hce": x_values["hce"],
            "authors": ["A. Diaw", "J. Lore", "J.S. Park", "S. Pascuale"],
            "owner": "ORNL",
            "converged": False,
            "doi": "",
            "access": "ml-project",
            "location": "ORNL cluster",
            "date": datetime.today().strftime('%Y-%m-%d'),
            "notes": ""
            }
        ]
    }   

    with open(os.path.join(run_dir, "params.json"), 'w') as f:
        json.dump(params, f, indent=2)

    for prt_file in glob.glob(os.path.join(run_dir, "*.prt")):
        os.remove(prt_file)
        print(f"🧹 Removed {prt_file}")

    exit()
    prt_path = os.path.join(run_dir, "b2mn.prt")
    if os.path.exists(prt_path):
        os.remove(prt_path)
        print(f"🧹 Removed existing b2mn.prt in {run_dir}")
    command = 'b2run -m "mpirun -np 12" b2mn > run.log'
    subprocess.run(command, shell=True, cwd=run_dir, check=True)

def run_sample(x):
    try:
        return cost4(x)
    except Exception as e:
        print(f"❌ Error running sample {x}: {e}")
        return None

    
# Parameter space
lb = [1.0, 1.0, 1.0, 0.1, 0.1]
ub = [5.0, 8.0, 7.5, 2.0, 2.0]
npts = 4

# Generate points and save to
#lhs_pts = lhs_samples(lb, ub, npts)

#np.savetxt("training.txt", lhs_pts, fmt="%.8f")

#exit()
# Load from file
#lhs_loaded = np.loadtxt("training.txt")

# If npts=1, ensure it's 2D
#if lhs_loaded.ndim == 1:
#    lhs_loaded = lhs_loaded.reshape(1, -1)

# Loop over each sample
#for x in lhs_loaded:
#    try:
#        result = cost4(x)  # or objective(x)
#    except Exception as e:
#        print(f"❌ Error running sample {x}: {e}")

# Load from training data
lhs_loaded = np.loadtxt("training.txt")

num_workers = min(10, len(lhs_loaded))  # Run 8

# If npts=1, ensure it's 2D
if lhs_loaded.ndim == 1:
    lhs_loaded = lhs_loaded.reshape(1, -1)

with ProcessPoolExecutor(max_workers=num_workers) as executor:
    futures = [executor.submit(run_sample, x) for x in lhs_loaded]
    for future in as_completed(futures):
        result = future.result()





