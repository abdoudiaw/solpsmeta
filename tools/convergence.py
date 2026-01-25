import os
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import netCDF4 as nc
from datetime import datetime
from pathlib import Path

def check_convergence(
    path,
    window="auto",               # int | "all" | "auto"
    rel_tol=0.02,                # ±2% band
    abs_tol=None,                # absolute band if set
    pos_idx=-1,
    in_band_frac=0.95,           # % of points in band required to pass
    plateau_w=80,                # rolling window for plateau detect (samples)
    plateau_hold=60,             # need this many consecutive samples "flat"
    save_plot=True,
    out_png="Figs/convergence_check.png",
):
    ...
    ds = nc.Dataset(path, "r")
    t = ds["timesa"][...]
    tesepa = ds["tesepa"][...]
    tesepi = ds["tesepi"][...]
    nesepa = ds["nesepa"][...]
    tmne   = ds["tmne"][...]

    def pick(a):
        a = np.asarray(a)
        return a if a.ndim == 1 else a[:, pos_idx]

    series_dict = {
        "tesepa": (pick(tesepa), r"$T_{e,sep}^{\rm OMP}$ (eV)"),
        "tesepi": (pick(tesepi), r"$T_{e,sep}^{\rm inboar}$ (eV)"),
        "nesepa": (pick(nesepa), r"$n_{e,sep}^{\rm OMP}$ [$\mathrm{m^{-3}}$]"),
        "tmne":   (pick(tmne),   r"Total number of particles"),
    }

    n = len(t)
    if n == 0:
        raise ValueError("Empty time array")

    # ---------- plateau detection (optional) ----------
    def robust_spread(y):
        y = np.asarray(y)
        med = np.median(y)
        p5, p95 = np.percentile(y, [5, 95])
        return (p95 - p5) / max(abs(med), 1e-12), med

    def detect_plateau(y, w=80, hold=60, tol=0.02):
        """Return start index of steady region or 0 if not found."""
        y = np.asarray(y)
        if len(y) < w:
            return 0
        spreads = np.empty(len(y)); spreads[:] = np.nan
        for i in range(w-1, len(y)):
            spreads[i], _ = robust_spread(y[i-w+1:i+1])
        # require 'hold' consecutive points below tol; pick first of last streak
        ok = (spreads <= tol)
        best_start = 0
        run = 0
        for i in range(len(ok)):
            run = run + 1 if ok[i] else 0
            if run >= hold:
                best_start = i - hold + 1
                break
        return max(best_start, 0)

    # choose window indices
    if isinstance(window, int):
        i0 = max(n - window, 0)
    elif window == "all":
        i0 = 0
    elif window == "auto":
        # pick the latest (most conservative) plateau start across variables
        i0_candidates = []
        for key, (yy, _) in series_dict.items():
            i0_candidates.append(detect_plateau(yy, w=plateau_w, hold=plateau_hold, tol=rel_tol))
        i0 = int(max(i0_candidates))  # start where *all* appear flat
    else:
        raise ValueError("window must be int | 'all' | 'auto'")

    tW = t[i0:]
    if len(tW) < 2:
        i0 = 0; tW = t

    results, all_pass = {}, True

    # ---------- plot ----------
    with mpl.style.context("classic"):
        FS = 18
        mpl.rc("font", size=FS); mpl.rc("xtick", labelsize=FS); mpl.rc("ytick", labelsize=FS)
        fig, axs = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
        axs = axs.flatten()

        for ax, (key, (y, ylab)) in zip(axs, series_dict.items()):
            yW = y[i0:]

            # metrics on window
            spread, median = robust_spread(yW)
            m, b = (0.0, yW[-1])
            if np.ptp(tW) > 0:
                m, b = np.polyfit(tW, yW, 1)
            rel_slope = m / max(abs(median), 1e-12)

            meanW = np.mean(yW)
            if abs_tol is not None:
                lo, hi = meanW - abs_tol, meanW + abs_tol
            else:
                lo, hi = meanW * (1 - rel_tol), meanW * (1 + rel_tol)

            frac_in = np.mean((yW >= lo) & (yW <= hi))
            band_ok = frac_in >= in_band_frac
            spread_ok = (spread <= rel_tol) if abs_tol is None else (np.ptp(yW) <= 2*abs_tol)
            key_pass = band_ok and spread_ok
            results[key] = dict(spread=spread, mean=meanW, slope=m,
                                rel_slope_perc_per_s=rel_slope*100, frac_in=frac_in, pass_=key_pass)
            all_pass &= key_pass

            # draw
            ax.plot(t, y, lw=2.2)
            ax.axvspan(t[i0], t[-1], alpha=0.08)                  # tested window
            ax.axhline(meanW, ls="--", lw=1.5)                    # window mean
            ax.fill_between(tW, lo, hi, alpha=0.10)               # tol band
            ax.set_ylabel(ylab); ax.grid(True, ls=":", lw=0.9)

            ann = (rf"spread$_{{95-5}}$={spread*100:.2f}%"
#                   + f"\nfrac-in-band={frac_in*100:.1f}%"
                   + f"\nrel slope={rel_slope*100:.2f}%/s")
            ax.text(0.02, 0.98, ann, transform=ax.transAxes, va="top", ha="left",
                    fontsize=FS-2, bbox=dict(boxstyle="round,pad=0.3", fc=("0.9" if key_pass else "1.0"), ec="0.6"))

            if "n_e" in ylab:
                ax.set_yscale("log")

        axs[-2].set_xlabel("time (s)"); axs[-1].set_xlabel("time (s)")
#        label = (f"±{rel_tol*100:.1f}%" if abs_tol is None else f"±{abs_tol} (abs)")
#        fig.suptitle(f"Window: {window} (start idx {i0}, {len(tW)} samples)  |  band = {label}  |  in-band≥{in_band_frac*100:.0f}%")
        fig.tight_layout(rect=[0,0,1,0.96])
        if save_plot:
            Path(os.path.dirname(out_png)).mkdir(parents=True, exist_ok=True)
            fig.savefig(out_png, dpi=300)
#        plt.close(fig)
        plt.show()

#    # logging & quit
#    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#    with open(os.path.join(os.path.dirname(path), "convergence.log"), "a") as log:
#        log.write(f"[{ts}] {path} window={window} i0={i0} n={len(tW)}\n")
#        for k, r in results.items():
#            log.write(f"  {k:<8} spread={r['spread']*100:6.2f}%  "
#                      f"slope={r['slope']:.3g}/s  rel_slope={r['rel_slope_perc_per_s']:.2f}%/s  "
#                      f"in-band={r['frac_in']*100:5.1f}%  {'PASS' if r['pass_'] else 'FAIL'}\n")
#        log.write("  ✅ Converged\n" if all_pass else "  ❌ Not converged\n")
#
#    if all_pass:
#        quit_path = os.path.join(os.path.dirname(path), "b2mn.exe.dir", ".quit")
#        os.makedirs(os.path.dirname(quit_path), exist_ok=True)
#        with open(quit_path, "w") as f:
#            f.write("converged\n")
#        print(f"✅ Converged — wrote {quit_path}")
#    else:
#        print("❌ Not converged — continuing simulation")

    return all_pass



if __name__ == "__main__":
#    check_convergence("../run_1p006_1p969_7p245_0p797_1p501/b2time.nc",
#                      n_window=10**9, rel_tol=0.5)
#    check_convergence("../run_1p006_1p969_7p245_0p797_1p501/b2time.nc", window="auto", rel_tol=0.02, in_band_frac=0.95)
    check_convergence("../run_1p006_1p969_7p245_0p797_1p501/b2time.nc", window="auto", rel_tol=0.2, in_band_frac=0.95)
