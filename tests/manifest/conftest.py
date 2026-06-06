import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "manifest"))

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_text():
    return (FIXTURES / "sample.dwarf.txt").read_text()
