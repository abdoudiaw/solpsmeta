#!/usr/bin/env python3
import argparse
import sqlite3
import numpy as np
from scipy.spatial import cKDTree


DEFAULT_COLS = ["puff_d2", "puff_ne", "ptot_w", "core_flux", "dna", "hci", "hce"]
DEFAULT_LOG_COLS = {"puff_d2", "puff_ne", "ptot_w", "core_flux"}  # huge dynamic range


def fetch_cases(db_path, cols, only_good=False):
    cols_sql = ", ".join(cols)
    where = ""
    if only_good:
        # “good” = converged OR returncode==0 (you can tighten this later)
        where = "WHERE (converged = 1 OR returncode = 0)"

    q = f"""
        SELECT case_id, run_dir, {cols_sql}, converged, returncode
        FROM cases
        {where}
    """

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(q)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise RuntimeError("No rows found in cases table (maybe your WHERE filter removed everything).")

    case_ids = [r[0] for r in rows]
    run_dirs = [r[1] for r in rows]
    conv = np.array([r[2 + len(cols)] for r in rows], dtype=int)
    rc = np.array([r[3 + len(cols)] for r in rows], dtype=int)

    X = np.array([r[2:2 + len(cols)] for r in rows], dtype=float)
    return case_ids, run_dirs, X, conv, rc


def transform(X, cols, log_cols):
    """Apply log10 transform to selected columns (safe for >0 only)."""
    X2 = X.copy()
    for j, name in enumerate(cols):
        if name in log_cols:
            # avoid log(0): treat <=0 as NaN (will be filtered out)
            bad = X2[:, j] <= 0
            X2[bad, j] = np.nan
            X2[:, j] = np.log10(X2[:, j])
    return X2


def build_tree(X):
    # Remove any rows containing NaN (e.g., from log-transform of <=0)
    good = np.all(np.isfinite(X), axis=1)
    Xg = X[good]
    if Xg.shape[0] == 0:
        raise RuntimeError("All rows were filtered out (NaNs after transform). Check your data/log columns.")
    tree = cKDTree(Xg)
    return tree, good


def parse_args():
    p = argparse.ArgumentParser(
        description="Query nearest SOLPS runs from cases.sqlite using a KDTree."
    )
    p.add_argument("--db", required=True, help="Path to cases.sqlite")
    p.add_argument("--k", type=int, default=1, help="Number of nearest neighbors to return")

    # Option A: pass full vector in column order
    p.add_argument(
        "--x",
        type=float,
        nargs="+",
        help="Query vector values in the same order as --cols (default: puff_d2 puff_ne ptot_w core_flux dna hci hce)",
    )

    # Option B: pass named values (friendlier)
    p.add_argument("--puff-d2", type=float)
    p.add_argument("--puff-ne", type=float)
    p.add_argument("--ptot-w", type=float)
    p.add_argument("--core-flux", type=float)
    p.add_argument("--dna", type=float)
    p.add_argument("--hci", type=float)
    p.add_argument("--hce", type=float)

    p.add_argument("--cols", nargs="+", default=DEFAULT_COLS, help="Which DB columns define the parameter space")
    p.add_argument(
        "--no-log",
        action="store_true",
        help="Disable log10 transform (by default logs puff_d2,puff_ne,ptot_w,core_flux)",
    )
    p.add_argument(
        "--only-good",
        action="store_true",
        help="Only consider runs with converged=1 OR returncode=0",
    )
    return p.parse_args()


def main():
    args = parse_args()
    cols = args.cols

    # Build query vector
    if args.x is not None:
        if len(args.x) != len(cols):
            raise ValueError(f"--x must have {len(cols)} values (one per --cols). Got {len(args.x)}.")
        q = np.array(args.x, dtype=float)
    else:
        # named inputs: must cover all cols
        mapping = {
            "puff_d2": args.puff_d2,
            "puff_ne": args.puff_ne,
            "ptot_w": args.ptot_w,
            "core_flux": args.core_flux,
            "dna": args.dna,
            "hci": args.hci,
            "hce": args.hce,
        }
        missing = [c for c in cols if mapping.get(c) is None]
        if missing:
            raise ValueError(
                "Missing named parameters for: " + ", ".join(missing) +
                "\nEither pass all named flags, or use --x ..."
            )
        q = np.array([mapping[c] for c in cols], dtype=float)

    # Load DB
    case_ids, run_dirs, X, conv, rc = fetch_cases(args.db, cols, only_good=args.only_good)

    # Transform space
    log_cols = set() if args.no_log else (DEFAULT_LOG_COLS.intersection(cols))
    X_t = transform(X, cols, log_cols)
    q_t = transform(q.reshape(1, -1), cols, log_cols).reshape(-1)

    # Build tree
    tree, good_mask = build_tree(X_t)
    good_idx = np.where(good_mask)[0]

    # Query
    k = max(1, int(args.k))
    dist, idx = tree.query(q_t, k=k)

    # Normalize output for k=1 vs k>1
    if k == 1:
        dist = np.array([dist])
        idx = np.array([idx])

    print(f"DB: {args.db}")
    print(f"cols: {cols}")
    print(f"log10: {sorted(list(log_cols)) if log_cols else 'OFF'}")
    print("query:", q.tolist())
    print()

    for rank, (d, local_i) in enumerate(zip(dist, idx), start=1):
        global_i = good_idx[int(local_i)]
        print(f"[{rank}] dist={float(d):.6g}  case_id={case_ids[global_i]}")
        print(f"     run_dir={run_dirs[global_i]}")
        print(f"     converged={int(conv[global_i])}  returncode={int(rc[global_i])}")
        print(f"     x={X[global_i].tolist()}")
        print()


if __name__ == "__main__":
    main()

