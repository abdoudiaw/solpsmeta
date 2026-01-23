# solpsmeta/cases/builder.py
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional, Iterable

DEFAULT_COPY_MODE = "copy"  # set to "symlink" if you want that as global default


def _clean_tag(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("/", "-")
    s = re.sub(r"[^A-Za-z0-9._\-]+", "_", s)
    return s


def make_case_from_template(
    warm_start_dir: str,
    out_root: str,
    case_id: str,
    label: Optional[str] = None,
    mode: str = DEFAULT_COPY_MODE,   # ✅ use the constant
    exist_ok: bool = False,
) -> str:
    """
    Create run_<case_id>__[label] under out_root by copying (or symlinking) warm_start_dir.

    mode:
      - "copy": deep copy (safe)
      - "symlink": symlink top-level entries (fast/small, but writes may hit the template)
    """
    src = Path(warm_start_dir).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"warm_start_dir not found: {src}")

    out = Path(out_root).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    run_name = f"run_{_clean_tag(case_id)}"
    if label:
        run_name += f"__{_clean_tag(label)}"

    dst = out / run_name

    if dst.exists():
        if exist_ok:
            return str(dst)
        raise FileExistsError(f"run_dir already exists: {dst}")

    if mode not in ("copy", "symlink"):
        raise ValueError("mode must be 'copy' or 'symlink'")

    if mode == "copy":
        shutil.copytree(src, dst)
        return str(dst)

    # mode == "symlink": link each top-level entry
    dst.mkdir()
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            os.symlink(str(item), str(target), target_is_directory=True)
        else:
            os.symlink(str(item), str(target))
    return str(dst)


def ensure_private_paths(run_dir: str, relpaths: Iterable[str]) -> None:
    """
    If run_dir was created via symlinks, and you're about to EDIT some files,
    this makes those files/directories "private" by replacing symlinks with real copies.

    Call this once before apply_edits().
    """
    rd = Path(run_dir).resolve()

    for rp in relpaths:
        p = (rd / rp)

        # If the path doesn't exist, skip (or raise if you prefer)
        if not p.exists() and not p.is_symlink():
            continue

        # If it's a symlink, replace it with a copy
        if p.is_symlink():
            real = p.resolve()  # where the symlink points
            p.unlink()

            if real.is_dir():
                shutil.copytree(real, p)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(real, p)

