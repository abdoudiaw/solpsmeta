import numpy as np
import matplotlib.pyplot as plt

# Load the data
data = np.load("solps_2d_images/solps_data.npy", allow_pickle=True).item()
images = data["images"]
parameters = data["parameters"]

# Choose index to plot
idx = 0  # Change to view another sample

# Extract image and parameters
img = images[idx]
params = parameters[idx]

# Plot
plt.figure(figsize=(6, 5))
plt.imshow(img)
plt.axis('off')
plt.title(f"GAS_PUFF={params[0]:.3f}, P_TOT={params[1]:.3f}\n"
          f"CORE_FLUX={params[2]:.3f}, DNA={params[3]:.3f}, HCI={params[4]:.3f}",
          fontsize=10)
plt.tight_layout()
plt.show()
