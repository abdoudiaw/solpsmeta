import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
import os
from datetime import datetime
import glob

def load_all_run_data(run_dirs):
    all_data = {'tesepa': [], 'tesepi': [], 'nesepm': [], 'tmne': [], 'timesa': []}
    labels = []

    for run_dir in run_dirs:
        ncfile = os.path.join(run_dir, "b2time.nc")
        try:
            data = nc.Dataset(ncfile, "r")
            timesa = data['timesa'][...]
            tesepa = data['tesepa'][..., -1]
            tesepi = data['tesepi'][..., -1]
            nesepm = data['nesepa'][..., -1]
            tmne   = data['tmne'][...]

            all_data['timesa'].append(timesa)
            all_data['tesepa'].append(tesepa)
            all_data['tesepi'].append(tesepi)
            all_data['nesepm'].append(nesepm)
            all_data['tmne'].append(tmne)
            labels.append(os.path.basename(run_dir))

        except Exception as e:
            print(f"⚠️ Skipped {run_dir}: {e}")

    return all_data, labels

def plot_combined(all_data, labels, out_dir='.'):
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    axs = axs.flatten()

    variables = ['tesepa', 'tesepi', 'nesepm', 'tmne']
    titles = ['Electron Temperature', 'Ion Temperature', 'Electron Density', 'Neutral Density']
    ylabels = ['Te [eV]', 'Ti [eV]', 'ne [m⁻³]', 'n₀ [m⁻³]']
    ylims = [(0, 200), (0, 200), (1e18, 5e20), (1e19, 5e20)]

    for i, var in enumerate(variables):
        for j, values in enumerate(all_data[var]):
            time = all_data['timesa'][j]
            axs[i].plot(time, values, label=labels[j])
        axs[i].set_title(titles[i])
        axs[i].set_xlabel("Time [s]")
        axs[i].set_ylabel(ylabels[i])
        axs[i].set_ylim(ylims[i])
        axs[i].grid(True)
        #axs[i].legend(fontsize='small')

    plt.tight_layout()
    out_path = os.path.join(out_dir, f"all_runs_4panel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    plt.savefig(out_path, dpi=150)
    plt.show()
    print(f"📊 Saved combined plot to: {out_path}")

if __name__ == "__main__":
    run_dirs = sorted(glob.glob("run_*"))
    if not run_dirs:
        print("No run_* directories found.")
    else:
        all_data, labels = load_all_run_data(run_dirs)
        plot_combined(all_data, labels)


