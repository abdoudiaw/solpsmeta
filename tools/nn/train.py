import torch
import nn_learner
import collections
import numpy as np
import matplotlib.pyplot as plt
import collections
import matplotlib as mpl
import random
import sklearn.metrics


dataset='solps_train.db'
model =nn_learner.retrain(db_path=dataset)
torch.save(model,f"diiid.pt")


# Plot True versus Predicted all DATA


Plotter1D = False

# Load model
print("PYTORCH VERSION", torch.__version__)
with torch.serialization.safe_globals([nn_learner.LearnerModel]):
    model = torch.load("diiid.pt", weights_only=False)

# Load dataset
#DB_PATH = '../solps_diiid.db'
DB_PATH = 'solps_test.db'
raw_dataset = nn_learner.getAllGNDData(DB_PATH)
OUTPUT_SLICE = nn_learner.SOLVER_INDEXES["output_slice"]

# Define inputs
Inputs = collections.namedtuple('Inputs', 'gas_puff p_tot core_flux dna hci r region')
Outputs = collections.namedtuple('Outputs', 'ne te ti po')
#Labels = ["$n_e$", "$T_e$", "$T_i$, "Potential"]
Labels = ["$n_e$", "$T_e$", "$T_i$", "Potential"]


# Define Inputs namedtuple
Inputs = collections.namedtuple('Inputs', 'gas_puff p_tot core_flux dna hci r region')

# Prepare containers
predictions = []
errbars = []

# Loop over dataset for individual predictions
for i, row in enumerate(raw_dataset):
    input_sample = Inputs(*row[:7])  # unpack inputs
    pred, err = model(input_sample)  # model returns unpacked Outputs
    predictions.append([pred.ne, pred.te, pred.ti, pred.po])
    errbars.append([err.ne, err.te, err.ti, err.po])

predictions = np.array(predictions)
errbars = np.array(errbars)

okay_prediction = model.iserrok(errbars)
point_badness = model.iserrok_fuzzy(errbars)
# Compute fuzzy error point-wise
point_badness = np.array([
    list(model.iserrok_fuzzy(Outputs(*err))) for err in errbars
])


n_targets = predictions.shape[1]
fig, axarr = plt.subplots(2, 2, figsize=(8, 8))
axarr = axarr.flatten()

for i, ax in enumerate(axarr[:n_targets]):
    ax.hist(point_badness[:, i], bins=30)
    ax.set_title(f"{Labels[i]} Relative Error")
    ax.set_xlabel("Relative Error")
    ax.set_ylabel("Count")
    ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("Figs/histo_trueVSpredicted.png", dpi=300)
plt.show()



Labels = ["$n_e$", "$T_e$", "$T_i$", "Potential"]

fig, axarr = plt.subplots(2, 2, figsize=(8, 8))
axarr = axarr.flatten()

print("Bad points:", (point_badness >= 1).any(axis=1).sum(axis=0))
true = raw_dataset[:, OUTPUT_SLICE]

for i, (p, t, bad, ax, eb) in enumerate(zip(predictions.T, true.T, point_badness.T, axarr, model.err_info)):
    plt.sca(ax)
    plt.title(Labels[i])
    plt.xlabel("True")
    plt.ylabel("Predicted")

    mm = min(min(p), min(t))
    xx = max(max(p), max(t))

    plt.plot((mm, xx), (mm, xx), lw=1, c='grey')
    plt.plot((mm, xx), (mm + eb, xx + eb), lw=1, c='grey', ls='--')
    plt.plot((mm, xx), (mm + 2 * eb, xx + 2 * eb), lw=1, c='grey', ls=':')
    plt.plot((mm, xx), (mm - eb, xx - eb), lw=1, c='grey', ls='--')
    plt.plot((mm, xx), (mm - 2 * eb, xx - 2 * eb), lw=1, c='grey', ls=':')

    colors = np.minimum(bad, 1)
    sc = plt.scatter(t, p, c=colors, s=5, cmap=plt.get_cmap('plasma'))
#    plt.colorbar()
    cbar = plt.colorbar(sc)
    cbar.set_label("flag")

    really_bad = (bad >= 1.0)
    plt.scatter(t[really_bad], p[really_bad], edgecolors='r', s=20, marker='o', c=[[0, 0, 0, 0]])

    rsq = sklearn.metrics.r2_score(t, p)
    plt.text(0.1, 0.9, "R² = {}".format(round(rsq, 3)), transform=ax.transAxes)

    margin = 0.1 * (xx - mm)
    plt.xlim(mm - margin, xx + margin)
    plt.ylim(mm - margin, xx + margin)

    plt.grid(alpha=0.3)
#    cbar = plt.colorbar(sc)
#    cbar.set_label("Error flag")

plt.tight_layout()
plt.savefig("Figs/trueVSpredicted.png", dpi=300)
plt.show()






# Plot 1D
if Plotter1D:
    r = np.loadtxt("../ds/dsr", unpack=True)
    region = 1

    # Pick 4 random cases from region 1
    region_mask = raw_dataset[:, 6] == region
    #unique_cases = np.unique(raw_dataset[region_mask][:, :5], axis=0)
    #selected_cases = unique_cases[:4]  # Pick first 4 for reproducibility

    rounded_cases = np.round(raw_dataset[region_mask][:, :5], decimals=6)
    unique_cases = np.unique(rounded_cases, axis=0)
    selected_cases = random.sample(list(unique_cases), 4)


    quantities = ['ne', 'te', 'ti', 'po']
    labels = [r"$n_e$", r"$T_e$", r"$T_i$", r"Potential"]
    scatter_colors = ['red', 'darkorange', 'purple', 'cyan']

    for idx, case in enumerate(selected_cases):
        gas_puff, p_tot, core_flux, dna, hci = case
        predicted_vals = []
        for ri in r:
            input_sample = Inputs(gas_puff, p_tot, core_flux, dna, hci, ri, region)
            prediction, errbar = model(input_sample)
            predicted_vals.append(prediction)
        predicted_vals = np.array(predicted_vals)

        # Mask for ground truth
        mask = (
            np.isclose(raw_dataset[:, 0], gas_puff) &
            np.isclose(raw_dataset[:, 1], p_tot) &
            np.isclose(raw_dataset[:, 2], core_flux) &
            np.isclose(raw_dataset[:, 3], dna) &
            np.isclose(raw_dataset[:, 4], hci) &
            (raw_dataset[:, 6] == region)
        )
        true_r = raw_dataset[mask][:, 5]
        true_data = raw_dataset[mask][:, OUTPUT_SLICE.start:OUTPUT_SLICE.start+4]

        # Create figure for this case
        
        with mpl.style.context('classic'):
            LW = 20
            plt.matplotlib.rc('xtick', labelsize=LW)
            plt.matplotlib.rc('ytick', labelsize=LW)
            mpl.rc('font', size=LW)
            mpl.rcParams['figure.figsize'] = 20, 12
            # Plot all 4 quantities
            fig, axes = plt.subplots(2, 2, figsize=(20, 12), sharex=True)

            for i, ax in enumerate(axes.flat):
                ax.plot(r, predicted_vals[:, i], label=f"Predicted {labels[i]}")
                ax.scatter(true_r, true_data[:, i], color='black', s=20, alpha=0.6, label=f"True {labels[i]}")
                ax.set_ylabel(labels[i])
                ax.set_xlabel("dsr (m)")
                ax.grid(True)
                ax.legend()

            plt.suptitle(
                f"Case {idx+1}: gas_puff={gas_puff:.2e}, p_tot={p_tot:.2e}, "
                f"core_flux={core_flux:.2e}, dna={dna:.3f}, hci={hci:.3f}",
                fontsize=20
            )


    #        plt.suptitle(f"Case {idx+1}", fontsize=22)
            plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # leave space for title
            plt.savefig(f"Figs/case_{idx+1}.png", dpi=300)
            plt.show()

