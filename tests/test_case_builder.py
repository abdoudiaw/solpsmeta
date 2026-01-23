# tests/test_case_builder.py
from __future__ import annotations

import os
from pathlib import Path

import pytest

from solpsmeta import SpeciesSpec, build_metadata_v2, make_case_from_template, apply_edits


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    t = tmp_path / "template_case"
    t.mkdir()

    # Minimal “SOLPS-ish” files for your regex editors.
    # Adjust these strings if your editors look for different patterns.

    _write(
        t / "b2.neutrals.parameters",
        """
&neutrals
nstrai=3,
gpfc(1,1)= 2.0, 0.0, 0.0,
gpfc(1,2)= 0.0, 0.0, 1.0,
userfluxparm(1,1)= 0.0, 0.0, 0.0,
/
""".lstrip(),
    )

    _write(
        t / "b2.boundary.parameters",
        """
&boundary
enepar(1,1)= 1.0000E+06, otherstuff
enipar(1,1)= 1.0000E+06, otherstuff
conpar(0,1,1)= 0.0000E+00, 0.0000E+00,
/
""".lstrip(),
    )

    _write(
        t / "b2.transport.parameters",
        """
&transport
parm_dna= 20*1.000000E+00
parm_hci= 20*1.000000E+00
parm_hce= 1.000000E+00
/
""".lstrip(),
    )

    return t


def test_make_case_from_template_and_apply_edits(tmp_path: Path, template_dir: Path) -> None:
    out_root = tmp_path / "runs"
    case_id = "abc123"
    run_dir = Path(make_case_from_template(str(template_dir), str(out_root), case_id, mode="copy"))

    assert run_dir.is_dir()
    assert (run_dir / "b2.neutrals.parameters").exists()

    species = SpeciesSpec(
        main_ion="D",
        impurities=["C", "Ne"],
        charge_state_ranges={"D": [0, 1], "C": [0, 6], "Ne": [0, 10]},
    )

    spec = build_metadata_v2(
        machine="DIII-D",
        campaign="unit_test",
        case_id=case_id,
        run_dir=str(run_dir),
        authors=["A. Diaw"],
        owner="ORNL",
        species=species,
        puff_targets={
            "D2": {"value": 2.5e21, "gpfc": [2, 0, 0]},
            "Ne": {"value": 1.0e19, "gpfc": [0, 0, 1]},
        },
        Pe_W=4.0e6,
        Pi_W=2.0e6,
        core_flux=1.2e20,
        transport={
            "units": "SI",
            "slots": 20,
            "dna": {"type": "global", "value": 1.1},
            "hci": {"type": "global", "value": 0.7},
            "hce": {"type": "global", "value": 0.7},
        },
        notes="pytest",
        converged=False,
    )

    # This is what you want to validate before touching libEnsemble.
    apply_edits(str(run_dir), spec)

    # sanity checks that something changed
    neutr = (run_dir / "b2.neutrals.parameters").read_text()
    assert "userfluxparm(1,1)" in neutr

    bnd = (run_dir / "b2.boundary.parameters").read_text()
    assert "enepar(1,1)" in bnd
    assert "conpar(0,1,1)" in bnd

    trn = (run_dir / "b2.transport.parameters").read_text()
    assert "parm_dna" in trn
    assert "parm_hci" in trn

