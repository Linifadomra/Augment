"""
conftest.py
Shared fixtures for the walker test suite.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT    = Path(__file__).resolve().parents[2]
WALKER       = REPO_ROOT / "tools" / "walker" / "walk.py"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Core runner fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def run_walker(tmp_path):
    """
    Returns a callable:
        run_walker(fixture_name_or_path, extra_args=[]) -> Path(output_dir)

    Accepts either a filename relative to fixtures/ or an absolute Path.
    Raises subprocess.CalledProcessError on non-zero exit so test failures
    surface immediately with the walker's stderr.
    """
    def _run(fixture, extra_args=None):
        if isinstance(fixture, str):
            header = FIXTURES_DIR / fixture
        else:
            header = Path(fixture)

        out_dir = tmp_path / "out"
        cmd = [
            sys.executable, str(WALKER),
            "--output-dir", str(out_dir),
            *(extra_args or []),
            str(header),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            pytest.fail(
                f"walker exited {result.returncode}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        return out_dir

    return _run


# ---------------------------------------------------------------------------
# Convenience helpers (imported by test modules)
# ---------------------------------------------------------------------------

def load_manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "symbols.json").read_text())


def get_symbol(manifest: dict, qualified_name: str) -> dict:
    for s in manifest["symbols"]:
        if s["symbol"] == qualified_name:
            return s
    raise KeyError(f"Symbol '{qualified_name}' not found in manifest.\n"
                   f"Available: {[s['symbol'] for s in manifest['symbols']]}")


def ctx_hpp(out_dir: Path) -> str:
    return (out_dir / "augment_ctx.hpp").read_text()


def trampolines_cpp(out_dir: Path) -> str:
    return (out_dir / "augment_trampolines.cpp").read_text()