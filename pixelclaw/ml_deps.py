"""
Ensure optional ML packages are installed at app startup.

Each entry in _OPTIONAL_PACKAGES is:
    (import_name, pip_name, conda_deps)

where conda_deps is a list of conda packages that must be installed first
(needed when a pip package has deps that require pre-built conda binaries).

To add a new dependency, append a tuple. Examples:
    ("segment_anything", "segment-anything", []),   # SAM; model weights ~375MB–2.4GB
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

_OPTIONAL_PACKAGES = [
    # rembg needs numba (via pymatting); numba must come from conda, not pip
    ("rembg", "rembg[cpu]", ["numba"]),
]


def ensure_packages() -> None:
    """Install any missing optional ML packages. Runs once at startup before InitWindow."""
    for import_name, pip_name, conda_deps in _OPTIONAL_PACKAGES:
        if importlib.util.find_spec(import_name) is not None:
            continue
        for dep in conda_deps:
            _conda_install(dep)
        _pip_install(pip_name)


def _conda_install(package: str) -> None:
    if importlib.util.find_spec(package) is not None:
        return
    print(f"[PixelClaw] Installing {package} (conda)...", flush=True)
    micromamba = _find_micromamba()
    env_name = Path(sys.prefix).name
    cmd = [micromamba, "install", "-n", env_name, "-c", "conda-forge", package, "-y"]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[PixelClaw] {package} installed.", flush=True)


def _pip_install(package: str) -> None:
    print(f"[PixelClaw] Installing {package} (pip)...", flush=True)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[PixelClaw] {package} installed.", flush=True)


def _find_micromamba() -> str:
    """Return the micromamba executable path."""
    import shutil
    path = shutil.which("micromamba")
    if path:
        return path
    # Common install location when not on PATH
    candidate = Path.home() / "micromamba" / "bin" / "micromamba"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError("micromamba not found; cannot install conda dependencies.")
