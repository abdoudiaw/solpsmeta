import os
import glob
import subprocess

def objective0(x, np=80, exe="b2mn_glibc"):
    """
    x: run directory (preferred), or a tag (optional convenience)
    """

    # If x looks like a path (contains '/' or is absolute), treat it as run_dir.
    # Otherwise treat it as a tag and build run_<tag> under cwd.
    if isinstance(x, str) and (os.path.isabs(x) or os.sep in x):
        run_dir = os.path.abspath(x)
    else:
        tag = str(x)
        run_dir = os.path.join(os.getcwd(), f"run_{tag}")

    os.makedirs(run_dir, exist_ok=True)

    # Remove any *.prt files
    for prt_file in glob.glob(os.path.join(run_dir, "*.prt")):
        try:
            os.remove(prt_file)
            print(f"🧹 Removed {prt_file}")
        except FileNotFoundError:
            pass

    # Remove known SOLPS outputs
    files_to_remove = [
        "b2mn.prt",
        "b2fparam",
        "b2fmovie",
        "b2fstate",
        "b2ftrace",
        "b2ftrack",
        "b2time.nc",
        "run.log",
    ]

    for name in files_to_remove:
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            os.remove(path)
            print(f"🧹 Removed {path}")

    # Run SOLPS with MPI, logging to run.log
    log_path = os.path.join(run_dir, "run.log")
    with open(log_path, "w") as logfile:
        proc = subprocess.Popen(
            ["mpirun", "-np", str(np), exe],
            cwd=run_dir,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,  # new process group
        )

    print(f"🚀 Launched SOLPS in {run_dir} (PID {proc.pid})")
    return proc.pid, run_dir

folder='/home/cloud/solps-runs/d3d/174310_LDRD/3500_D+C+Ne/warm_start'
objective0(folder)

# or
#objective0("case_001")  # becomes ./run_case_001



