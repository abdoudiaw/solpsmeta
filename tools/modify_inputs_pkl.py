import os
import pickle

# Normalization factors
norm_factors = [1e21, 1e6, 1e20, 1, 1]

def normalize(vals, factors):
    return tuple(round(v / f, 3) for v, f in zip(vals, factors))

# Loop through folders
for folder in os.listdir('.'):
    if not folder.startswith("K_(") or not os.path.isdir(folder):
        continue

    old_path = os.path.abspath(folder)

    try:
        # Fix parsing issue here
        raw_vals = folder.replace("K_(", "").replace(")", "").split(", ")
        original_vals = tuple(float(v) for v in raw_vals)
    except ValueError:
        print(f"⚠️ Skipping: {folder}, can't parse values")
        continue

    # Normalize and create new name
    normalized_vals = normalize(original_vals, norm_factors)
    new_folder = f'K_({", ".join(str(v) for v in normalized_vals)})'
    new_path = os.path.abspath(new_folder)

    if os.path.exists(new_path):
        print(f"⚠️ Skipping rename: {new_folder} already exists")
        continue

    # Rename folder
    os.rename(old_path, new_path)
    print(f"✅ Renamed: {folder} → {new_folder}")

    # Modify input.pkl
    input_path = os.path.join(new_path, 'input.pkl')
    if os.path.exists(input_path):
        with open(input_path, 'wb') as f:
            pickle.dump(normalized_vals, f)
        print(f"   ↪️ Updated input.pkl")
    else:
        print(f"   ⚠️ No input.pkl found")


