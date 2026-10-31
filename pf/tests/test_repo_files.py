import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_upstream_file_is_a_release_tag():
    text = (ROOT / "pf" / "UPSTREAM").read_text()
    assert re.fullmatch(r"v\d+\.\d+\.\d+\n?", text), text


def test_upstream_matches_package_version():
    version = json.loads((ROOT / "package.json").read_text())["version"]
    assert (ROOT / "pf" / "UPSTREAM").read_text().strip() == "v" + version
