import os
import re
import time
import numpy as np
import pprint
import subprocess
from mystic.tools import random_state
import signal
import time

from block_analysis import check_solps_convergence
import threading
from queue import Queue
from datetime import datetime
import numpy as np
import shutil
import netCDF4 as nc
import json
from scipy.stats import qmc
import pandas as pd
from scipy.spatial import KDTree
import re
import glob

from sync_to_dropbox import sync_to_dropbox_and_cleanup

    # Run SOLPS in background with MPI
    # --------------------------------------
    log_path = os.path.join(run_dir, "run.log")
    with open(log_path, "w") as logfile:
        proc = subprocess.Popen(
            ["mpirun", "-np", "90", "b2mn_glibc"],
            cwd=run_dir,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,  # start a new process group (critical!)
        )

