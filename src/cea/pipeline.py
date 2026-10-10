"""The compiler pipeline: lexical, syntax and semantic phases on one source text (plan 007).

``compile_source`` is the interface the corpus test (tests/test_corpus_compile.py)
and every later milestone call. It never raises on bad input: each phase
reports through one ErrorSink (PRD F1) and the next phase always runs
(docs/error-recovery.md §1, invariant 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cea import ast as A
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
    _sink: ErrorSink | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        """True iff no record is fatal (PRD F4: a file with only warnings still compiles)."""
        return not any(r.severity == "fatal" for r in self.errors)

    def summary(self) -> str:
        """PRD F4 summary line, e.g. "2 fatal, 3 warnings"; delegates to ErrorSink.summary()."""
        assert self._sink is not None, "CompileResult was not built by compile_source()"
        return self._sink.summary()


def compile_source(source: str, filename: str) -> CompileResult:
    """Run all three phases. ``filename`` is for display only. root_id stays == id until F2 (milestone 2)."""
    sink = ErrorSink(source)
    lr = lex(source, sink)
    program = parse(lr, sink)
    analyze(program, sink, lr.stdio_include)
    return CompileResult(errors=sink.records, program=program, tokens=lr.tokens, _sink=sink)
