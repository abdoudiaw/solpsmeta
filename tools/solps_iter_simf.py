import os
import re
import time
import numpy as np
import pprint
import subprocess
from mystic.tools import random_state
from convergence import check_convergence
import threading
from queue import Queue
from datetime import datetime
import numpy as np
import shutil
import netCDF4 as nc
import json
from scipy.stats import qmc
import pandas as pd
from scipy.spatial import KDTree
import re
import glob
import dropbox
import json

# Load Dropbox tokens
#with open("dropbox_tokens.json", "r") as f:
#    tokens = json.load(f)

#DROPBOX_TOKEN = tokens["access_token"]

DROPBOX_DB_PATH = "/SOLPS DB"

#dbx = dropbox.Dropbox(DROPBOX_TOKEN)

from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from dropbox.oauth import OAuth2Session

with open("dropbox_tokens.json", "r") as f:
    tokens = json.load(f)

# Create an OAuth2 session that can refresh the token
oauth2_session = OAuth2Session(
    consumer_key="tp2407mqd8ndrcc",
    consumer_secret="8wyr7gm8kyk856w",
    refresh_token=tokens["refresh_token"],
    access_token=tokens["access_token"],
    token_access_type="offline"
)

def save_new_token(oauth2_session):
    def save_token_callback(token_data):
        # Save only the access token (refresh stays the same)
        tokens["access_token"] = token_data["access_token"]
        if "expires_at" in token_data:
            tokens["expires_at"] = token_data["expires_at"]
        with open("dropbox_tokens.json", "w") as f:
            json.dump(tokens, f, indent=2)
        print("🔁 Access token refreshed and saved.")
    oauth2_session._token_updater = save_token_callback

save_new_token(oauth2_session)


dbx = dropbox.Dropbox(oauth2_session)

def build_kdtree_dropbox(db_folder):
    entries = dbx.files_list_folder(db_folder).entries

    # Only keep folders that start with "run_"
    folder_list = [
        entry.name for entry in entries
        if isinstance(entry, dropbox.files.FolderMetadata) and entry.name.startswith("run_")
    ]

    points = []
    for folder in folder_list:
        tag = folder.replace("run_", "")
        try:
            x_vals = [float(x.replace("p", ".")) for x in tag.split("_")]
            points.append(x_vals)
        except ValueError:
            print(f"⚠️ Skipping malformed folder name: {folder}")

    from scipy.spatial import KDTree
    tree = KDTree(points)
    return tree, folder_list, points


# Generate date string
today_date = datetime.today().strftime('%Y-%m-%d')


def load_x_values(folder):
    path = os.path.join(folder, "params.json")
    try:
        with open(path) as f:
            data = json.load(f)

        # Extract from the list inside "solps-iter-params"
        params = data["solps-iter-params"][0]

        return [
            float(params["gas_puff"]),
            float(params["Pe"]),
            float(params["core_flux"]),
            float(params["dna"]),
            float(params["hci"]),
        ]
    except Exception as e:
        print(f"❌ Failed to load {path}: {e}")
        return None

def build_kdtree(base_dir):
    points = []
    folders = []

    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        x_vals = load_x_values(folder_path)
        if x_vals is not None and len(x_vals) == 5:
            points.append(x_vals)
            folders.append(folder)

    tree = KDTree(points)
    return tree, folders, np.array(points)
 
def monitor_convergence(folder_name, result_queue, interval_sec=3600, max_checks=20):
    """
    Checks for convergence and sends final tesepa to result_queue.
    """
    nc_path = os.path.join(folder_name, "b2time.nc")
    for i in range(max_checks):
        time.sleep(interval_sec)
        if os.path.exists(nc_path):
            print(f"🔍 [{folder_name}] Checking convergence... (check {i+1})")
            try:
                converged = check_convergence(nc_path, save_plot=False)
                if converged:
                    print(f"✅ [{folder_name}] Converged — extracting final tesepa")
                    data = nc.Dataset(nc_path, "r")
                    tesepa = data["tesepa"][...]
                    final_te = tesepa[-1, -1]
                    result_queue.put((folder_name, final_te, 0))  # 0 = success
                    return
            except Exception as e:
                print(f"⚠️ Error checking convergence: {e}")
    result_queue.put((folder_name, None, 1))  # 1 = failed or timeout

def _sanitize_val(val, scale=1.0):
    norm = val / scale
    return f"{norm:.3f}".replace(".", "p")

def _set_psol_value(content, value):
    return content.replace("PSOL = ...", f"PSOL = {value:.6e}")

def _set_conpar_density(content, value):
    return content.replace("CONPAR = ...", f"CONPAR = {value:.6e}")

def _set_transport_values(content, params):
    for key, val in params.items():
        content = content.replace(f"{key} = ...", f"{key} = {val:.6e}")
    return content

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

#def _set_psol_value(content, value):
#    return re.sub(r"PSOL\s*=\s*[\d\.eE\+\-]+", f"PSOL = {value:.6e}", content)

def _set_conpar_density(content, value):
    return re.sub(r"CONPAR\s*=\s*[\d\.eE\+\-]+", f"CONPAR = {value:.6e}", content)

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

def copy_b2fstate_from_closest(closest_folder, db_path, run_dir):
    src = os.path.join(db_path, closest_folder, "b2fstate")
    dst = os.path.join(run_dir, "b2fstati")
    
    try:
        shutil.copy(src, dst)
        print(f"✅ Copied b2fstate from {src} to {dst}")
    except Exception as e:
        print(f"❌ Failed to copy b2fstate: {e}")

def copy_b2fstate_from_closest(closest_folder, db_path, run_dir):
    dropbox_src = f"{db_path}/{closest_folder}/b2fstate"
    local_dst = os.path.join(run_dir, "b2fstati")

    try:
        metadata, res = dbx.files_download(dropbox_src)
        with open(local_dst, "wb") as f:
            f.write(res.content)
        print(f"✅ Copied b2fstate from Dropbox ({dropbox_src}) to {local_dst}")
    except Exception as e:
        print(f"❌ Failed to download b2fstate from Dropbox: {e}")
        

def objective(x):
    print("calling objective with params x", x)
    
    # Generate unique run directory
    tag = "_".join([
        _sanitize_val(x[0], 1),
        _sanitize_val(x[1], 1),
        _sanitize_val(x[2], 1),
        _sanitize_val(x[3]),
        _sanitize_val(x[4]),
    ])


    original_wd = os.getcwd()

    # Check if case was already run
    record_file = "evaluated_cases.csv"
    if os.path.exists(record_file):
        df = pd.read_csv(record_file)
        if tag in df["case_id"].values:
            print(f"⚠️ Case {tag} already evaluated. Skipping.")
            return None
            

    run_dir = os.path.join(os.getcwd(), f"run_{tag}")
    os.makedirs(run_dir, exist_ok=True)

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
    tree, folder_list, points = build_kdtree_dropbox(DROPBOX_DB_PATH)

#    tree, folder_list, points = build_kdtree(db_dir)
    dist, idx = tree.query(x_denorm)
    closest_folder = folder_list[idx]
    print(f"✅ Closest match: {closest_folder} (distance: {dist:.2e})")

    # Print the folder (run_dir) name
    print(f"Processing folder: {os.path.abspath(run_dir)}")

    for file_name, params in input_files.items():
        path = os.path.join(run_dir, file_name)
        print(f"Modifying file: {file_name}")  # Print each file being modified

        print("Writing to:", path)
        
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

        with open(path, 'w') as f:  # Make sure to write to the same path
            f.write(content)


    copy_b2fstate_from_closest(closest_folder, DROPBOX_DB_PATH, run_dir)

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


    prt_path = os.path.join(run_dir, "b2mn.prt")
    if os.path.exists(prt_path):
        os.remove(prt_path)
        print(f"🧹 Removed existing b2mn.prt in {run_dir}")
    # Run SOLPS in background with MPI
    command =  r'b2run -m \"mpirun -np 32\" b2mn > run.log'
    subprocess.run(command, shell=True, cwd=run_dir, check=True)


    # Wait for result file
    nc_path = os.path.join(run_dir, "b2time.nc")
    while not os.path.exists(nc_path):
        print("⏳ Waiting for b2time.nc...")
        time.sleep(5)

    # Load and return result
    data = nc.Dataset(nc_path, "r")
    tesepa = data["tesepa"][...]
    final_te = tesepa[-1, -1]

    x = x_values  # now x is the dictionary
    print(f"✅ Final Te = {final_te:.2e} for case {x['case_id']} with inputs: "
      f"gas_puff={x['gas_puff']:.1e}, Pe={x['Pe']:.1e}, core_flux={x['core_flux']:.1e}, "
      f"dna={x['dna']}, hci/hce={x['hci']}")

    # Ensure the script is executable
    os.chmod("cleaner.sh", 0o755)
    # Call it directly with tcsh
    subprocess.run("source cleaner.sh", shell=True, executable="/bin/tcsh", cwd=run_dir)

    
    #os.chdir(original_wd)
 # # After computing final_te, append results
 #   df_new = pd.DataFrame([{
 #       "case_id": tag,
 #       "gas_puff": x_values["gas_puff"],
 #       "Pe": x_values["Pe"],
 #       "core_flux": x_values["core_flux"],
 #       "dna": x_values["dna"],
 #       "hci": x_values["hci"],
 #       "hce": x_values["hce"],
 #       "final_te": final_te,
 #   }])
#
#    if os.path.exists(record_file):
#        df_new.to_csv(record_file, mode="a", header=False, index=False)
#    else:
#        df_new.to_csv(record_file, index=False)
#        
#    return final_te


#    4.23122554 7.73184932 4.44770899 1.32735502 1.01424952
#    4.23122554 7.73184932 4.44770899 1.32735502 1.01424952
#x = np.array([4.23122554, 7.73184932, 4.44770899, 1.32735502, 1.01424952])
#te = objective(x)


