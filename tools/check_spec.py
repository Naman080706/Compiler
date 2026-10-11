"""Cross-check docs/error-catalog.md against docs/language-spec.md.

Fails if any catalog row is malformed or cites a rule_ref the spec does not define.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "language-spec.md").read_text(encoding="utf-8")
CATALOG = (ROOT / "docs" / "error-catalog.md").read_text(encoding="utf-8")

CATEGORIES = {
    "malformed-token", "unclosed-delimiter", "missing-semicolon", "syntax-structure",
    "undeclared-identifier", "redeclaration", "type-mismatch", "function-misuse",
    "control-flow", "unused-code", "gcc-diagnostic",
}
PREFIX_PHASE = {"LEX": "lexical", "SYN": "syntax", "SEM": "semantic", "WRN": "semantic", "GCC": None}  # GCC: any phase


def defined_names():
    names = set()
    for block in re.findall(r"```ebnf\n(.*?)```", SPEC, re.S):
        names.update(re.findall(r"^([A-Za-z_]+)\s*=", block, re.M))
    sem_ids = set(re.findall(r"^### (sem\.[a-z_]+)\s*$", SPEC, re.M))
    return names, sem_ids


def main():
    grammar, sem_ids = defined_names()
    errors, seen, used_sem = [], set(), set()
    rows = [
        [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        for line in CATALOG.splitlines()
        if re.match(r"^\|\s*(LEX|SYN|SEM|WRN|GCC)-", line)
    ]
    for row in rows:
        if len(row) != 7:
            errors.append(f"expected 7 columns, got {len(row)}: {row[0]}")
            continue
        code, phase, severity, category, ref, message, example = row
        prefix = code.split("-")[0]
        if code in seen:
            errors.append(f"duplicate code {code}")
        seen.add(code)
        if PREFIX_PHASE[prefix] is None:
            if phase not in ("lexical", "syntax", "semantic"):
                errors.append(f"{code}: unknown phase {phase}")
        elif PREFIX_PHASE[prefix] != phase:
            errors.append(f"{code}: phase {phase} does not match prefix {prefix}")
        if severity != ("warning" if prefix == "WRN" or code in ("GCC-WARNING", "GCC-NOTE") else "fatal"):
            errors.append(f"{code}: wrong severity {severity}")
        if category not in CATEGORIES:
            errors.append(f"{code}: unknown category {category}")
        if ref == "<production>":
            if prefix != "SYN":
                errors.append(f"{code}: only SYN codes may use <production>")
        elif ref.startswith("sem."):
            if ref not in sem_ids:
                errors.append(f"{code}: rule_ref {ref} has no '### {ref}' heading in spec")
            used_sem.add(ref)
        elif ref not in grammar:
            errors.append(f"{code}: rule_ref {ref} is not a rule in any ebnf block")
        if not message or not example:
            errors.append(f"{code}: empty message or example")
    for orphan in sorted(sem_ids - used_sem):
        errors.append(f"spec rule {orphan} is not referenced by any code")
    for e in errors:
        print("ERROR:", e)
    if errors:
        return 1
    print(f"OK: {len(rows)} codes, {len(grammar)} grammar/lexical rules, {len(sem_ids)} semantic rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
