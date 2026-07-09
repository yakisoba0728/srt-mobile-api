import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def load_text_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")
