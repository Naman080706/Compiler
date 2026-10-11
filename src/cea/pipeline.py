"""The compiler pipeline: lexical, syntax and semantic phases on one source text (plan 007).

``compile_source`` is the interface the corpus test (tests/test_corpus_compile.py)
and every later milestone call. It never raises on bad input: each phase
reports through one ErrorSink (PRD F1) and the next phase always runs
(docs/error-recovery.md §1, invariant 1). After the three phases, F2
clustering (plan 009, ``cea.cluster``) fills every record's ``root_id``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
from cea.cluster import Cluster, assign_roots, cluster_view
from cea import gcc_fallback
from cea.diagnostics import ErrorSink
from cea.lexer import lex
from cea.parser import parse
from cea.records import ErrorRecord
from cea.semantic import analyze
from cea.tokens import Token


@dataclass
class CompileResult:
    errors: list[ErrorRecord]       # sink.records, creation order
    program: A.Program
    tokens: list[Token]
    clusters: list[Cluster] = field(default_factory=list)   # F2: one per root, roots in (line, column) order
    _sink: ErrorSink | None = field(default=None, repr=False, compare=False)
    engine: str = "cea"             # "cea" (our compiler) or "gcc" (the gcc fallback)
    engine_note: str | None = None  # why gcc ran, or that it could not (gcc missing)

    @property
    def ok(self) -> bool:
        """True iff no record is fatal (PRD F4: a file with only warnings still compiles)."""
        return not any(r.severity == "fatal" for r in self.errors)

    def summary(self) -> str:
        """PRD F4 summary line, e.g. "2 fatal, 3 warnings"; delegates to ErrorSink.summary()."""
        assert self._sink is not None, "CompileResult was not built by compile_source()"
        return self._sink.summary()


ENGINES = ("auto", "cea", "gcc")
UNSUPPORTED_CODES = frozenset({"SYN-UNSUPPORTED-FEATURE", "LEX-UNSUPPORTED-DIRECTIVE"})
FALLBACK_NOTE = "This program uses a feature outside the course subset, so it was analysed by gcc."
FORCED_NOTE = "Analysed by gcc (requested with the gcc engine)."


def compile_source(source: str, filename: str, engine: str = "auto") -> CompileResult:
    """Run all three phases, then F2 clustering. ``filename`` is for display only.

    ``engine``: "cea" always uses our compiler; "gcc" always uses the gcc fallback; "auto" (default) uses our
    compiler and falls back to gcc when it reports SYN-UNSUPPORTED-FEATURE or LEX-UNSUPPORTED-DIRECTIVE.
    If gcc is needed but not installed, our own result is returned with an ``engine_note`` saying so.
    """
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, not {engine!r}")
    own = _compile_cea(source)
    wants_gcc = engine == "gcc" or (engine == "auto" and any(r.code in UNSUPPORTED_CODES for r in own.errors))
    if not wants_gcc:
        return own
    sink = ErrorSink(source)
    if not gcc_fallback.run_gcc(source, sink):
        own.engine_note = gcc_fallback.GCC_MISSING_NOTE
        return own
    errors = sink.records
    assign_roots(errors, own.program)
    return CompileResult(errors=errors, program=own.program, tokens=own.tokens, clusters=cluster_view(errors),
                         _sink=sink, engine="gcc", engine_note=FORCED_NOTE if engine == "gcc" else FALLBACK_NOTE)


def _compile_cea(source: str) -> CompileResult:
    sink = ErrorSink(source)
    lr = lex(source, sink)
    program = parse(lr, sink)
    analyze(program, sink, lr.includes)
    errors = sink.records
    assign_roots(errors, program)                       # F2 (plan 009): last, after every phase
    return CompileResult(errors=errors, program=program, tokens=lr.tokens,
                         clusters=cluster_view(errors), _sink=sink)
