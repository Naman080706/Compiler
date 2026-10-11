"""The gcc fallback (src/cea/gcc_fallback.py) and the engine switch of compile_source / the CLI."""
import json
import shutil

import pytest

from cea import gcc_fallback as G
from cea.cli import main as cli_main
from cea.diagnostics import ErrorSink
from cea.pipeline import compile_source

needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not on PATH")

GOTO_OK = "int main(void) {\n    int n = 0;\n    goto end;\nend:\n    return n;\n}\n"
GOTO_BAD = "int main(void) {\n    int n = 0;\n    goto end;\nend:\n    return m;\n}\n"
FIXTURE = json.dumps([
    {"kind": "warning", "message": "unused variable 'x'", "children": [],
     "locations": [{"caret": {"line": 3, "byte-column": 9, "column": 9}}]},
    {"kind": "error", "message": "'y' undeclared (first use in this function)",
     "locations": [{"caret": {"line": 4, "byte-column": 5}, "finish": {"line": 4, "byte-column": 5}}],
     "children": [{"kind": "note", "message": "each undeclared identifier is reported only once",
                   "locations": [{"caret": {"line": 4, "byte-column": 5}}]}]},
    {"kind": "error", "message": "expected ';' before 'return'", "children": [],
     "locations": [{"caret": {"line": 5, "byte-column": 7}}]},
    {"kind": "note", "message": "previous declaration of 'f' was here", "children": [],
     "locations": [{"caret": {"line": 1, "byte-column": 5}}]},
])


def records_of(diags):
    sink = ErrorSink("a\nb\nc\nd\ne\n")
    G.report_all(diags, sink)
    return sink.records


# ---------------------------------------------------------------- pure parts
@pytest.mark.parametrize("message,phase", [
    ("stray '@' in program", "lexical"),
    ("missing terminating \" character", "lexical"),
    ("unterminated comment", "lexical"),
    ("invalid suffix \"abc\" on integer constant", "lexical"),
    ("unknown escape sequence: '\\q'", "lexical"),
    ("expected ';' before 'return'", "syntax"),
    ("expected expression before ')' token", "syntax"),
    ("unknown type name 'Strin'", "syntax"),
    ("invalid preprocessing directive #foo", "syntax"),
    ("expected declaration or statement at end of input", "syntax"),
    ("'y' undeclared (first use in this function)", "semantic"),
    ("assignment to expression with array type", "semantic"),
    ("unused variable 'x'", "semantic"),
])
def test_phase_heuristic(message, phase):
    assert G.guess_phase(message) == phase


def test_json_diagnostics_become_records_with_linked_notes():
    recs = records_of(G.parse_json(FIXTURE))
    assert [(r.code, r.phase, r.severity, r.line, r.column) for r in recs] == [
        ("GCC-WARNING", "semantic", "warning", 3, 9),
        ("GCC-ERROR", "semantic", "fatal", 4, 5),
        ("GCC-NOTE", "semantic", "warning", 4, 5),
        ("GCC-ERROR", "syntax", "fatal", 5, 7),
        ("GCC-NOTE", "semantic", "warning", 1, 5),
    ]
    assert recs[2].caused_by == recs[1].id            # a child note belongs to its parent
    assert recs[4].caused_by == recs[3].id            # a top-level note follows the last error
    assert recs[0].caused_by is None and recs[1].caused_by is None
    assert recs[1].message == "gcc: 'y' undeclared (first use in this function)" and recs[1].found == "y"
    assert all(r.rule_ref == "sem.gcc_fallback" and r.language == "c" for r in recs)


def test_clusters_show_notes_as_symptoms():
    from cea.cluster import assign_roots, cluster_view
    sink = ErrorSink("a\nb\nc\nd\ne\n")
    G.report_all(G.parse_json(FIXTURE), sink)
    recs = sink.records
    assign_roots(recs)
    view = cluster_view(recs)
    assert [(c.root.code, [s.code for s in c.symptoms]) for c in view] == [
        ("GCC-WARNING", []), ("GCC-ERROR", ["GCC-NOTE"]), ("GCC-ERROR", ["GCC-NOTE"])]


def test_text_output_is_parsed_when_json_is_unreadable():
    text = ("t.c: In function 'main':\nt.c:4:5: error: 'y' undeclared (first use in this function)\n"
            "t.c:4:5: note: each undeclared identifier is reported only once\nt.c:3:9: warning: unused variable 'x' [-Wunused-variable]\n")
    assert G.parse_json(text) is None
    diags = G.parse_text(text)
    assert [(d.kind, d.line, d.column) for d in diags] == [("error", 4, 5), ("note", 4, 5), ("warning", 3, 9)]


def test_json_with_no_diagnostics_is_an_empty_list():
    assert G.parse_json("[]") == [] and G.parse_json("") == []


def test_location_defaults_when_gcc_gives_none():
    (d,) = G.parse_json(json.dumps([{"kind": "error", "message": "no input files"}]))
    assert (d.line, d.column) == (1, 1)


# ---------------------------------------------------------------- real gcc
@needs_gcc
def test_run_gcc_reports_real_diagnostics():
    sink = ErrorSink(GOTO_BAD)
    assert G.run_gcc(GOTO_BAD, sink) is True
    errs = [r for r in sink.records if r.code == "GCC-ERROR"]
    assert any("'m' undeclared" in r.message and r.line == 5 for r in errs)
    assert all(r.phase in ("lexical", "syntax", "semantic") for r in sink.records)


@needs_gcc
def test_gcc_json_format_is_usable():
    assert G.run_gcc_raw(GOTO_OK) == []
    diags = G.run_gcc_raw("int main(void) {\n    int x = 1\n    return x;\n}\n")
    assert any(d.kind == "error" and d.line == 3 and "before 'return'" in d.message for d in diags)


# ---------------------------------------------------------------- engine switch
@needs_gcc
def test_auto_falls_back_to_gcc_for_unsupported_features():
    r = compile_source(GOTO_OK, "t.c")
    assert r.engine == "gcc" and r.ok and r.errors == [] and "outside the course subset" in r.engine_note
    r = compile_source(GOTO_BAD, "t.c")
    assert r.engine == "gcc" and not r.ok and r.summary() == "1 fatal, 1 warning"
    assert [c.root.code for c in r.clusters] == ["GCC-WARNING", "GCC-ERROR"]


@needs_gcc
def test_directive_also_triggers_the_fallback():
    r = compile_source("#ifdef X\nint a;\n#endif\nint main(void) { return 0; }\n", "t.c")
    assert r.engine == "gcc" and r.ok


def test_engine_cea_never_calls_gcc(monkeypatch):
    monkeypatch.setattr(G, "gcc_path", lambda: pytest.fail("gcc must not run"))
    r = compile_source(GOTO_OK, "t.c", engine="cea")
    assert r.engine == "cea" and r.engine_note is None
    assert any(e.code == "SYN-UNSUPPORTED-FEATURE" for e in r.errors)


def test_plain_programs_stay_on_our_compiler(monkeypatch):
    monkeypatch.setattr(G, "gcc_path", lambda: pytest.fail("gcc must not run"))
    r = compile_source("int main(void) {\n    int *p = 0;\n    return p == 0;\n}\n", "t.c")
    assert r.engine == "cea" and r.ok


@needs_gcc
def test_engine_gcc_is_forced_even_for_supported_programs():
    r = compile_source("int main(void) {\n    return y;\n}\n", "t.c", engine="gcc")
    assert r.engine == "gcc" and "requested" in r.engine_note and not r.ok


def test_missing_gcc_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(G, "gcc_path", lambda: None)
    r = compile_source(GOTO_OK, "t.c")
    assert r.engine == "cea" and "gcc is not installed" in r.engine_note
    assert any(e.code == "SYN-UNSUPPORTED-FEATURE" for e in r.errors)       # our own result is still returned
    assert compile_source(GOTO_OK, "t.c", engine="gcc").engine_note == G.GCC_MISSING_NOTE


def test_unknown_engine_is_a_value_error():
    with pytest.raises(ValueError):
        compile_source(GOTO_OK, "t.c", engine="clang")


# ---------------------------------------------------------------- CLI
@needs_gcc
def test_cli_engine_option(tmp_path, capsys):
    f = tmp_path / "t.c"
    f.write_text(GOTO_BAD, encoding="utf-8")
    assert cli_main([str(f)]) == 1
    out = capsys.readouterr().out
    assert "GCC-ERROR" in out and "note: This program uses a feature outside the course subset" in out
    assert cli_main([str(f), "--engine", "cea"]) == 1
    assert "SYN-UNSUPPORTED-FEATURE" in capsys.readouterr().out
    assert cli_main([str(f), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"] == "gcc" and payload["engine_note"]


def test_cli_says_when_gcc_is_missing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(G, "gcc_path", lambda: None)
    f = tmp_path / "t.c"
    f.write_text(GOTO_OK, encoding="utf-8")
    cli_main([str(f)])
    assert "gcc is not installed" in capsys.readouterr().out
