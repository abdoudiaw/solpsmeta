#import os
#import numpy as np
#import pandas as pd
#from skimage.io import imread
#from tqdm import tqdm
#
## Config
#IMAGE_DIR = "/Users/42d/ML_Projects/Tokamak_Pulse_Simulation_ML/scripts/solps_2d_images"
#OUTPUT_ARRAY_DIR = os.path.join(IMAGE_DIR, "arrays")
#CSV_PATH = os.path.join(IMAGE_DIR, "image_parameters.csv")
#
## Create output directory
#os.makedirs(OUTPUT_ARRAY_DIR, exist_ok=True)
#
## List all relevant files
#image_files = [f for f in os.listdir(IMAGE_DIR) if f.startswith("te_run_") and f.endswith(".png")]
#print(f"Found {len(image_files)} images.")
#
## Storage for parameters
#records = []
#
## Loop through files
#for file in tqdm(sorted(image_files), desc="Processing images"):
#    file_path = os.path.join(IMAGE_DIR, file)
#
#    # Load image
#    img = imread(file_path)
#
#    # Save as .npy
#    array_filename = file.replace(".png", ".npy")
#    np.save(os.path.join(OUTPUT_ARRAY_DIR, array_filename), img)
#
#    # Extract parameters from filename
#    param_str = file.replace("te_run_", "").replace(".png", "")
#    param_values = [float(s.replace("p", ".")) for s in param_str.split("_")]
#
#    # Store record
#    records.append({
#        "filename": file,
#        "array_file": array_filename,
#        "GAS_PUFF": param_values[0],
#        "P_TOT": param_values[1],
#        "CORE_FLUX": param_values[2],
#        "DNA": param_values[3],
#        "HCI": param_values[4]
#    })
#
## Save CSV
#df = pd.DataFrame(records)
#df.to_csv(CSV_PATH, index=False)
#print(f"\n✅ Saved parameter CSV to: {CSV_PATH}")
#print(f"✅ Saved .npy arrays to: {OUTPUT_ARRAY_DIR}")
#
#


import os
import numpy as np
from skimage.io import imread
from tqdm import tqdm

# Config
IMAGE_DIR = "/Users/42d/ML_Projects/Tokamak_Pulse_Simulation_ML/scripts/solps_2d_images"
OUTPUT_PATH = os.path.join(IMAGE_DIR, "solps_data.npy")

# List all image files
image_files = sorted([f for f in os.listdir(IMAGE_DIR) if f.startswith("te_run_") and f.endswith(".png")])
print(f"Found {len(image_files)} images.")

# Prepare storage
images = []
parameters = []

# Loop through image files
for file in tqdm(image_files, desc="Processing images"):
    file_path = os.path.join(IMAGE_DIR, file)

    # Load image
    img = imread(file_path)
    images.append(img)

    # Extract numerical parameters from filename
    param_str = file.replace("te_run_", "").replace(".png", "")
    param_values = [float(s.replace("p", ".")) for s in param_str.split("_")]
    parameters.append(param_values)

# Convert to arrays
images = np.array(images)
parameters = np.array(parameters)

# Save both in a single .npy file as a dictionary
np.save(OUTPUT_PATH, {"images": images, "parameters": parameters})
print(f"\n✅ Saved all data to: {OUTPUT_PATH}")
print(f"📊 Images shape: {images.shape}")
print(f"🔢 Parameters shape: {parameters.shape}")
