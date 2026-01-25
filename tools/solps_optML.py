#!/usr/bin/env python
# adapted from XRD example at: hhttps://github.com/abdoudiaw/Efficient-Sampling/tree/master/code
# Diaw May 2025
"""
optimization of 6-input cost function using online learning of a surrogate
"""
import os
from mystic.samplers import SparsitySampler
from mystic.monitors import LoggingMonitor
from mystic.solvers import PowellDirectionalSolver
from mystic.termination import NormalizedChangeOverGeneration as NCOG
from ouq_models import WrapModel, InterpModel
from emulators import cost4 as cost, x4 as target, bounds4 as bounds
from solps_iter_simf import objective as model

# create model
cost4 = lambda x: model(x)

# set boundaries: puff rate, power on e/i
# core density, perp diffusion coefficient, diffusivity
bounds = [
    [1E+21, 5E+21],
    [1.0e6, 8.0e6],
    [1.0e19, 7.5e20],
    [0.1, 2.0],
    [0.1, 2.0]
]

# set boundaries: puff rate, power on e/i, core density, perp diffusion coefficient, diffusivity
bounds = [
    [1E+21, 5E+21],
    [1.0e6, 8.0e6],
    [2.0e20, 2.0e20],
    [0.3, 0.3],
    [1.0, 1.0]
]

bounds = [
    [1.0, 5],
    [1.0, 8.0],
    [2., 2.],
    [0.3, 0.3],
    [1.0, 1.0]
]

bounds = [
    [1.0, 5.0],
    [1.0, 8.0],
    [0.1, 7.5],
    [0.1, 2.0],
    [0.1, 2.0]
]

# prepare truth (i.e. an 'expensive' model)
nx = 4; ny = None

# remove any prior cached evaluations of truth
import shutil
if os.path.exists("truth"): shutil.rmtree("truth")
if os.path.exists("error.txt"): os.remove("error.txt")
if os.path.exists("log.txt"): os.remove("log.txt")

try: # parallel maps
    from pathos.maps import Map
    from pathos.pools import ProcessPool, ThreadPool, SerialPool
    #pmap = Map(SerialPool) #ProcessPool
    #pmap = Map(ProcessPool)
    pmap = Map(ProcessPool(nodes=4))

except ImportError:
    pmap = None


#truth = WrapModel('truth', cost4, nx=nx, ny=ny, cached=False, pmap=pmap)
#truth = WrapModel('truth', cost4, nx=nx, ny=ny, cached=False)#archive)

truth = WrapModel('truth', cost4, nx=nx, ny=ny, cached=False, pmap=pmap)

# generate a training dataset by sampling truth
data = truth.sample(bounds, pts=[1, 1, 1, 1, 1], pmap=pmap)  # Total 30 training points

exit()

# shutdown mapper
if pmap is not None:
    pmap.close(); pmap.join(); pmap.clear()

# create an inexpensive surrogate for truth
surrogate = InterpModel("surrogate", nx=nx, ny=ny, data=truth, smooth=0.0,
                        noise=0.0, method="thin_plate", extrap=False)

# iterate until error (of candidate minimum) < 1e-3
N = 5
import numpy as np
import mystic._counter as it
counter = it.Counter()
tracker = LoggingMonitor(1, filename='error.txt', label='error')
from mystic.abstract_solver import AbstractSolver
from mystic.termination import VTR
loop = AbstractSolver(nx)
loop.SetTermination(VTR(1e-3)) #XXX: VTRCOG, TimeLimits, etc?
loop.SetEvaluationLimits(maxiter=500)
loop.SetGenerationMonitor(tracker)
while not loop.Terminated():

    # fit the surrogate to data in truth database
    surrogate.fit(data=data)

    # find the first-order critical points of the surrogate
    s = SparsitySampler(bounds, lambda x: surrogate(x, axis=None), npts=N,
                        maxiter=500, maxfun=10000, id=counter.count(N),
                        stepmon=LoggingMonitor(1, label='output'),
                        solver=PowellDirectionalSolver,
                        termination=NCOG(1e-6, 10))
    s.sample_until(terminated=all)
    xdata = [list(i) for i in s._sampler._all_bestSolution]
    ysurr = s._sampler._all_bestEnergy

    # evaluate truth at the same input as the surrogate critical points
    ytrue = list(map(truth, xdata))
    # add most recent candidate extrema to truth database
    data.load(xdata, ytrue)

    # compute absolute error between truth and surrogate at candidate extrema
    idx = np.argmin(ytrue)
    error = abs(np.array(ytrue) - ysurr)
    print("truth: %s @ %s" % (ytrue[idx], xdata[idx]))
    print("candidate: %s; error: %s" % (ysurr[idx], error[idx]))
    print("error ave: %s; error max: %s" % (error.mean(), error.max()))
    print("evaluations of truth: %s" % len(data))

    # save to tracker if less than current best
    ysave = error # track error when learning surrogate
    if len(tracker) and tracker.y[-1] < ysave[idx]:
        tracker(*tracker[-1])
    else: tracker(xdata[idx], ysave[idx])

# get the results at the best parameters from the truth database
xbest = tracker[-1][0]
#ybest = archive[tuple(xbest)]
ybest = data[data.coords.index(xbest)].value

# print the best parameters
print(f"Best solution is {xbest} with Rwp {ybest}")


