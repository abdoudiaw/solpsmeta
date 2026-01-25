
import sqlite3
import collections
import json
import pandas as pd
# ---- Helper Functions ----

def insert_dataframe_to_db(df, dbname, table="SOLPSDIIID"):
    """Create SQLite table and insert dataframe."""
    sql_db = sqlite3.connect(dbname, timeout=45.0)
    cursor = sql_db.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            gas_puff REAL,
            p_tot REAL,
            core_flux REAL,
            dna REAL,
            hci REAL,
            r REAL,
            region INTEGER,
            ne REAL,
            te REAL,
            ti REAL,
            po REAL
        );
    """)

    insert_query = f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    for row in df.itertuples(index=False):
        cursor.execute(insert_query, row)

    sql_db.commit()
    cursor.close()
    sql_db.close()
    print(f"✅ Saved to SQLite database: {dbname}")


def load_input_parameters(dbx, path, INPUT_COL_ORDER):
    """Load simulation input parameters and compute total power."""
    try:
        _, res = dbx.files_download(path)
        data = json.loads(res.content.decode("utf-8"))["solps-iter-params"][0]
        pe, pi = data.get("Pe"), data.get("Pi")
        return {
            "gas_puff": data.get("gas_puff"),
            "core_flux": data.get("core_flux"),
            "dna": data.get("dna"),
            "hci": data.get("hci"),
            "p_tot": pe + pi if pe and pi else None
        }
    except Exception as e:
        print(f"⚠️ Failed to load params.json: {e}")
        return {key: None for key in INPUT_COL_ORDER}

def load_input_parameters(dbx, path, keys):
    try:
        _, res = dbx.files_download(path)
        data = json.loads(res.content.decode("utf-8"))["solps-iter-params"][0]
        pe, pi = data.get("Pe"), data.get("Pi")

        if not all(k in data for k in ["gas_puff", "core_flux", "dna", "hci"]) or pe is None or pi is None:
            return None

        return {
            "gas_puff": data["gas_puff"],
            "core_flux": data["core_flux"],
            "dna": data["dna"],
            "hci": data["hci"],
            "p_tot": pe + pi
        }
    except Exception as e:
        print(f"⚠️ Error reading {path}: {e}")
        return None

def subset_to_dataframe(subset, full_dataset):
    """Convert PyTorch Subset to DataFrame for SQLite writing."""
    rows = []
    for i in subset.indices:
        x, y = full_dataset[i]  # x: [7], y: [2]
        row = list(x.numpy()) + list(y.numpy())
        rows.append(row)

    columns = ['gas_puff', 'p_tot', 'core_flux', 'dna', 'hci', 'r', 'region',  # x
               'te', 'ne']  # y — adjust names if needed
    return pd.DataFrame(rows, columns=columns)
