import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())
