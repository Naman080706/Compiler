"""Shared helpers for the corpus tests (plan 003). Stdlib only.

Test modules import it as ``import corpus_lib``. pytest puts the ``tests/``
folder on sys.path because that folder has no ``__init__.py``.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "corpus"
CATALOG = ROOT / "docs" / "error-catalog.md"
SPLITS = ("dev", "heldout", "valid")
SIDECAR_SUFFIX = ".expected.json"
CODE_ROW = re.compile(r"^\| (LEX|SYN|SEM|WRN)-")


def load_catalog():
    """Return {code: {"phase", "severity", "category"}} parsed from docs/error-catalog.md."""
    codes = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if CODE_ROW.match(line):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            codes[cells[0]] = {"phase": cells[1], "severity": cells[2], "category": cells[3]}
    return codes


def c_files(split=None):
    """Sorted list of (split, path) for every .c file in the corpus, or in one split."""
    out = []
    for s in SPLITS if split is None else (split,):
        out += [(s, p) for p in sorted((CORPUS / s).glob("*.c"))]
    return out


def sidecar_files(split=None):
    """Sorted list of (split, path) for every *.expected.json file."""
    out = []
    for s in SPLITS if split is None else (split,):
        out += [(s, p) for p in sorted((CORPUS / s).glob("*" + SIDECAR_SUFFIX))]
    return out


def sidecar_for(c_path):
    return c_path.with_name(c_path.stem + SIDECAR_SUFFIX)


def c_for(sidecar_path):
    return sidecar_path.with_name(sidecar_path.name[: -len(SIDECAR_SUFFIX)] + ".c")


def load_sidecar(c_path):
    return json.loads(sidecar_for(c_path).read_text(encoding="utf-8"))


def line_count(c_path):
    return len(c_path.read_text(encoding="utf-8").splitlines())
