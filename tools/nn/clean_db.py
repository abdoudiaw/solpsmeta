import torch
import sklearn.metrics
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
#import _nn_learner
import nn_learner
import torch
from nn_learner import SOLVER_INDEXES
import collections


if __name__=="__main__":
    print("PYTORCH VERSION",torch.__version__)
    DB_PATH='../solps_diiid.db'
    indices = SOLVER_INDEXES
    raw_dataset = nn_learner.getAllGNDData(DB_PATH)
#
    output_location = SOLVER_INDEXES["output_slice"]
    print(output_location)

    GAS_PUFF, P_TOT, CORE_FLUX, DNA, HCI, R, REGION = range(7)
    OUTPUT_SLICE = nn_learner.SOLVER_INDEXES["output_slice"]

    # Split input and output
    inputs = raw_dataset[:, :7]
    ne_te = raw_dataset[:, OUTPUT_SLICE]
    true_r = raw_dataset[:, R]

    # Group by unique input combinations (excluding r)
    unique_keys = np.unique(inputs[:, [GAS_PUFF, P_TOT, CORE_FLUX, DNA, HCI, REGION]], axis=0)

    te_threshold = 1e7
    bad_groups = []

    for i, key in enumerate(unique_keys):
        mask = np.all(np.isclose(inputs[:, [GAS_PUFF, P_TOT, CORE_FLUX, DNA, HCI, REGION]], key), axis=1)
        r_vals = inputs[mask][:, R]
        ne_vals = ne_te[mask][:, 0]
        te_vals = ne_te[mask][:, 1]

        if np.any(te_vals > te_threshold):
            print(f"⚠️ Group {i+1}: gas_puff={key[0]:.2e}, p_tot={key[1]:.2e}, core_flux={key[2]:.2e}, dna={key[3]:.3f}, hci={key[4]:.3f}, region={int(key[5])}")
            bad_groups.append(key)
            continue  # skip plotting this group

    import sqlite3

    DB_PATH = '../solps_diiid.db'
    table_name = "SOLPSDIIID"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"🧹 Removing {len(bad_groups)} bad groups from the database...")

    for key in bad_groups:
        gas_puff, p_tot, core_flux, dna, hci, region = key  # key is [0:6]

        # Use a DELETE query with proper precision tolerance
        cursor.execute(f"""
            DELETE FROM {table_name}
            WHERE
                ABS(gas_puff - ?) < 1e-8 AND
                ABS(p_tot - ?) < 1e-3 AND
                ABS(core_flux - ?) < 1e13 AND
                ABS(dna - ?) < 1e-6 AND
                ABS(hci - ?) < 1e-6 AND
                region = ?
        """, (gas_puff, p_tot, core_flux, dna, hci, int(region)))

        print(f"❌ Deleted group: gas_puff={gas_puff:.2e}, p_tot={p_tot:.2e}, region={int(region)}")

    conn.commit()
    conn.close()
    print("✅ Database cleanup complete.")

