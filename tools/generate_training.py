from numpy import savetxt
from scipy.stats import qmc

def lhs_samples(lb, ub, npts=100):
    dim = len(lb)
    sampler = qmc.LatinHypercube(d=dim)
    sample = sampler.random(n=npts)  # shape (npts, dim)
    return qmc.scale(sample, lb, ub)

# Parameter space
lb = [1.0, 1.0, 1.0, 0.1, 0.1]
ub = [5.0, 8.0, 7.5, 2.0, 2.0]

npts = 1000
# Generate points and save to
lhs_pts = lhs_samples(lb, ub, npts)
savetxt("training.txt", lhs_pts, fmt="%.8f")


