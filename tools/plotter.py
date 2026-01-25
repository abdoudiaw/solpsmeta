import os
import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from datetime import datetime

def check_convergence(path, n_last=100, threshold=10., save_plot=True):
    log_path = os.path.join(os.path.dirname(path), "convergence.log")
    try:
        data = nc.Dataset(path, "r")
        timesa = data['timesa'][...]
        tesepa = data['tesepa'][...]
        tesepi = data['tesepi'][...]
        nesepm = data['nesepa'][...]
        tmne   = data['tmne'][...]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


        indices = slice(-n_last, None)
        tesepa_tail = tesepa[:, -1]
        tesepi_tail = tesepi[:, -1]
        nesepm_tail = nesepm[:, -1]
        tmne_tail   = tmne ##[indices]

        
        def relative_spread(arr):
            return (np.max(arr) - np.min(arr)) / np.min(arr)

        params = {
            'tesepa': tesepa_tail,
            'tesepi': tesepi_tail,
            'nesepm': nesepm_tail,
            'tmne':   tmne_tail
        }

        if save_plot:
            fig, axs = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
            axs = axs.flatten()
            times_tail = timesa #[indices]

            for i, (name, values) in enumerate(params.items()):
                axs[i].plot(times_tail, values)
               # axs[i].set_title(f"{name} (spread: {results[name]*100:.2f}%)")
                axs[i].set_ylabel(name)
                axs[i].grid(True)

            axs[2].set_xlabel("Time [s]")
            axs[3].set_xlabel("Time [s]")
            plt.suptitle("Convergence Check Over Last Steps")
            plt.tight_layout(rect=[0, 0, 1, 0.96])

            out_dir = os.path.dirname(path)
            out_path = os.path.join(out_dir, f"convergence_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            plt.savefig(out_path, dpi=150)
            plt.show()
            print(f"📈 Plot saved to: {out_path}")

# how to deal with hunged cases ---> energy flux ZZZZ
        all_converged = True
        
        return all_converged

    except Exception as e:
        msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Error: {e}"
        print(msg)
        with open(log_path, "a") as log:
            log.write(msg + "\n")
        return False


import os
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc

def _resolve_nc_path(path_or_dir: str) -> str:
    """Return path to b2time.nc given either a dir or a file path."""
    if os.path.isdir(path_or_dir):
        p = os.path.join(path_or_dir, "b2time.nc")
    else:
        p = path_or_dir
    if not os.path.isfile(p):
        raise FileNotFoundError(f"Could not find b2time.nc at: {p}")
    return p

def _series_along_time(arr: np.ndarray, times_len: int) -> np.ndarray:
    """
    Return a 1D series over time:
      - If arr is 1D and matches times_len, return as-is.
      - Else, find an axis whose length == times_len and treat it as time.
      - Reduce (take last index) over all other axes.
    """
    a = np.asarray(arr)
    if a.ndim == 1 and a.size == times_len:
        return a

    # Find axis matching the time length
    candidates = [ax for ax, s in enumerate(a.shape) if s == times_len]
    axis_t = candidates[0] if candidates else (a.ndim - 1)  # fallback: last axis

    # Move time axis to front, then take last index along all others
    a = np.moveaxis(a, axis_t, 0)  # shape: (T, ...)
    while a.ndim > 1:
        a = a[..., -1]  # pick last along remaining non-time axes
    return a  # shape: (T,)

def _tail_idx(n: int, n_last: int) -> slice:
    return slice(max(0, n - int(n_last)), None)

def _rel_spread(y: np.ndarray) -> float:
    """(max - min) / max(min, eps) with safety for near-zero denominators."""
    y = np.asarray(y)
    if y.size == 0 or not np.isfinite(y).any():
        return np.nan
    ymin = np.nanmin(y)
    ymax = np.nanmax(y)
    denom = np.nanmax([abs(ymin), 1e-12])
    return float((ymax - ymin) / denom)

def _load_case(path_or_dir: str):
    p = _resolve_nc_path(path_or_dir)
    with nc.Dataset(p, "r") as ds:
        timesa = np.array(ds["timesa"][...])  # time stamps
        tesepa = np.array(ds["tesepa"][...])  # Te (separatrix, atoms)
        tesepi = np.array(ds["tesepi"][...])  # Te (separatrix, ions)
        nesepa = np.array(ds["nesepa"][...])  # ne (separatrix)  <-- fixed name
        tmne   = np.array(ds["tmne"][...])    # usually dt or a monitor series

    T = len(timesa)
    series = {
        "tesepa": _series_along_time(tesepa, T),
        "tesepi": _series_along_time(tesepi, T),
        "nesepa": _series_along_time(nesepa, T),
        "tmne":   _series_along_time(tmne,   T),
    }
    return timesa, series

def check_convergence_compare(path_a: str,
                              path_b: str,
                              n_last: int = 100,
                              threshold: float = 0.10,
                              labels=("case A", "case B"),
                              save_plot: bool = True):
    """
    Compare two runs on one figure. threshold is relative spread for 'converged'.
    Returns: dict summary with per-case spreads and booleans.
    """
    # Load both cases
    tA, sA = _load_case(path_a)
    tB, sB = _load_case(path_b)

    # Tail windows per case
    iA = _tail_idx(len(tA), n_last)
    iB = _tail_idx(len(tB), n_last)

    # Compute relative spreads for each metric on tail
    names = ["tesepa", "tesepi", "nesepa", "tmne"]
    spreadsA = {k: _rel_spread(sA[k][iA]) for k in names}
    spreadsB = {k: _rel_spread(sB[k][iB]) for k in names}
    convA = {k: (spreadsA[k] <= threshold) for k in names}
    convB = {k: (spreadsB[k] <= threshold) for k in names}

    # Plot
    fig, axs = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    axs = axs.flatten()
    titles = {
        "tesepa": r"$T_e$@sep (atom)",
        "tesepi": r"$T_e$@sep (ion)",
        "nesepa": r"$n_e$@sep",
        "tmne":   r"$t_{mne}$",
    }

    for ax, name in zip(axs, names):
        ax.plot(tA[iA], sA[name][iA], label=f"{labels[0]}  (spread={spreadsA[name]*100:.2f}%)")
        ax.plot(tB[iB], sB[name][iB], label=f"{labels[1]}  (spread={spreadsB[name]*100:.2f}%)", linestyle="--")
        ax.set_title(titles[name])
        ax.set_xlabel("time [s]")
        ax.set_ylabel(name)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9)

    plt.suptitle(f"Convergence (last {n_last} samples) — {labels[0]} vs {labels[1]}")
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = None
    if save_plot:
        # Save next to case A by default
        out_dir = os.path.dirname(_resolve_nc_path(path_a))
        out_path = os.path.join(out_dir, f"convergence_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(out_path, dpi=150)
        print(f"📈 Plot saved to: {out_path}")

    plt.show()

    return {
        "labels": labels,
        "spreads": {labels[0]: spreadsA, labels[1]: spreadsB},
        "converged": {labels[0]: convA, labels[1]: convB},
        "threshold": threshold,
        "plot_path": out_path,
    }

if __name__ == "__main__":
    # Example usage: compare two directories OR two b2time.nc files
    res = check_convergence_compare(
        "run_2p459_2p107_1p915_1p934_1p714/b2time.nc",  # dir OK
        "run_4p055_2p577_1p875_1p218_1p532/b2time.nc",  # file path OK
        n_last=200,
        threshold=0.08,
        labels=("old KD-TREE", "new baseline"),
        save_plot=True
    )
    print(res)

#
#if __name__ == "__main__":
#    converged = check_convergence("run_2p459_2p107_1p915_1p934_1p714/b2time.nc")
#


