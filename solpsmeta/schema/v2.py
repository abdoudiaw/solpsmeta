# solpsmeta/schema/v2.py
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SpeciesSpec:
    main_ion: str
    impurities: List[str]
    charge_state_ranges: Dict[str, List[int]]

    @property
    def list(self) -> List[str]:
        return [self.main_ion] + list(self.impurities)

def species_label(species: SpeciesSpec) -> str:
    return "_".join([species.main_ion] + list(species.impurities))

def _species_label(species) -> str:
    species = _coerce_species(species)
    return "_".join(species.list)   # e.g., D_C_Ne

def meta_builder(
    machine: str,
    campaign: str,
    case_id: str,
    run_dir: str,
    authors: List[str],
    owner: str,
    species: SpeciesSpec,
    puff_targets: Dict[str, Dict[str, Any]],
    Pe_W: float,
    Pi_W: float,
    core_flux: float,
    transport: Dict[str, Any],
    notes: str = "",
    converged: bool = False,
    solps_version: str = "",
    git_repo: str = "",
    git_commit: str = "",
    time_dependence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema": "solpsmeta",
        "machine": machine,
        "campaign": campaign,
        "case": {
            "case_id": case_id,
            "created": datetime.today().strftime("%Y-%m-%d"),
            "owner": owner,
            "authors": authors,
            "location": {
                "site": "ORNL",
                "cluster": os.environ.get("HOSTNAME", "unknown"),
                "path": run_dir,
            },
            "status": {"converged": converged, "notes": notes},
        },
        "inputs": {
            "power": {"Pe_W": Pe_W, "Pi_W": Pi_W},
            "core": {"particle_flux_s-1": core_flux},
            "species": {
                "list": species.list,
                "roles": {"main_ion": species.main_ion, "impurities": species.impurities},
                "charge_state_ranges": species.charge_state_ranges,
            },
            "gas_puffing": {
                "units": "s-1",
                "model": "userfluxparm(1,1)",
                "targets": puff_targets,
            },
            "transport": transport,
            "time_dependence": time_dependence or {"mode": "steady_state"},
        },
        "provenance": {
            "code": {
                "solps_version": solps_version,
                "git": {"repo": git_repo, "commit": git_commit},
            }
        },
    }


def _coerce_species(species):
    # Accept SpeciesSpec or dict with same keys
    if isinstance(species, SpeciesSpec):
        return species
    if isinstance(species, dict):
        return SpeciesSpec(
            main_ion=species["main_ion"],
            impurities=species.get("impurities", []),
            charge_state_ranges=species.get("charge_state_ranges", {}),
        )
    raise TypeError(f"species must be SpeciesSpec or dict, got {type(species)}")
    


def _git_info(repo_dir):
    repo_dir = os.path.abspath(repo_dir)

    def run(cmd):
        r = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
        if r.returncode != 0:
            return ""
        return r.stdout.strip()

    commit = run(["git", "rev-parse", "HEAD"])
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    remote = run(["git", "remote", "get-url", "origin"])
    dirty  = (run(["git", "status", "--porcelain"]) != "")

    return {
        "repo": remote,
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
    }
