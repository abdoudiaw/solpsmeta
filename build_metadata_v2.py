
import os, json, shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional

@dataclass
class SpeciesSpec:
    main_ion: str
    impurities: List[str]
    charge_state_ranges: Dict[str, List[int]]  # e.g. {"D":[0,1], "C":[0,6]}

    @property
    def list(self) -> List[str]:
        return [self.main_ion] + self.impurities


def build_metadata_v2(
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
    time_dependence: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:

    return {
        "schema": "solps-run-metadata-v2",
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
            "time_dependence": time_dependence or {"mode": "steady_state"}

        },
        "provenance": {
            "code": {
                "solps_version": solps_version,
                "git": {"repo": git_repo, "commit": git_commit},
            },
            "files_modified": [
                {
                    "file": "b2.neutrals.parameters",
                    "operation": "set_userflux_value",
                    "fields": ["inputs.gas_puffing.targets.*.value"],
                },
                {
                    "file": "b2.boundary.parameters",
                    "operation": "set_psol_value + set_conpar_density",
                    "fields": ["inputs.power.Pe_W", "inputs.core.particle_flux_s-1"],
                },
                {
                    "file": "b2.transport.parameters",
                    "operation": "set_transport_values",
                    "fields": ["inputs.transport.dna", "inputs.transport.hci", "inputs.transport.hce"],
                },
            ],
        },
    }
