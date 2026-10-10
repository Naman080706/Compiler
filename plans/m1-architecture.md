# Milestone 1 architecture contract (shared by plans 005, 006, 007)

Written by the advisor on 2026-10-10 against `main` @ `3af5d50`. This file is the **single source of truth for names and interfaces** across the milestone-1 plans. A plan may add private helpers, but it must not rename, drop, or change the type of anything defined here. If a plan finds this contract unworkable, it STOPs and reports. It does not diverge.

Normative inputs (read them; this file does not repeat them):
- `docs/language-spec.md`: grammar (EBNF rule names), types, `sem.*` rules.
- `docs/error-catalog.md`: the 37 codes, message templates, and the "Choosing among syntax codes" rules 0–5.
- `docs/error-recovery.md`: lexer, parser and semantic recovery, `caused_by` rules R1–R8 (plus amendments from plan 004), locations, and the 8 traces T1–T7.
- `tests/corpus/README.md` §6: the `compile_source` contract the corpus test checks.

## 1. Package layout

Python ≥ 3.11, **standard library only** (no runtime dependencies). Source lives in `src/cea/`. `pyproject.toml` already puts `src/` on pytest's path. "cea" stands for compiler error assistant.

| Module | Owner plan | Responsibility |
|---|---|---|
| `src/cea/__init__.py` | 005 | Package docstring only. |
| `src/cea/catalog.py` | 005 | Parse `docs/error-catalog.md` into `CatalogEntry` objects. |
| `src/cea/records.py` | 005 | `Position`, `ErrorRecord`. |
| `src/cea/diagnostics.py` | 005 | `ErrorSink`, the **error interceptor** (PRD F1). It is the only way to create a record. |
| `src/cea/tokens.py` | 005 | `TokenKind`, `Token`, keyword and operator tables. |
| `src/cea/lexer.py` | 005 | `lex()`: the lexical phase and recovery (`docs/error-recovery.md` §3). |
| `src/cea/ast.py` | 006 | AST node dataclasses (§4 below). Named `ast.py` inside the package; always import it as `from cea import ast as A` so it never shadows the stdlib `ast`. |
| `src/cea/parser.py` | 006 | `parse()`: the syntax phase and recovery (§4 of error-recovery), rules R1/R2, and the code-selection rules. |
| `src/cea/semantic.py` | 007 | `analyze()`: the semantic phase, `<error>` type, R3–R8. |
| `src/cea/pipeline.py` | 007 | `compile_source()`, `CompileResult`. **Created last**: its existence switches on `tests/test_corpus_compile.py`. |
| `src/cea/cli.py`, `src/cea/__main__.py` | 007 | `python -m cea FILE.c [--json]`. `__main__.py` contains only `from cea.cli import main` and `raise SystemExit(main())`; **`cli.py` is the only module allowed to call `print`**. |

**Rule (PRD F1: "No phase may print directly to the console").** No module except `cli.py` may call `print(` or write to `sys.stdout`/`sys.stderr`. Plan 005 adds a test that greps `src/cea/*.py` for `print(` and allows it only in `cli.py`.

## 2. Records and the interceptor (plan 005)

```python
# records.py
@dataclass(frozen=True)
class Position:
    line: int
    column: int

@dataclass
class ErrorRecord:
    # PRD schema fields, in PRD order
    id: str                 # "E-0001", "E-0002", ... in creation order
    phase: str              # "lexical" | "syntax" | "semantic"
    code: str               # a catalog code
    severity: str           # "fatal" | "warning", always from the catalog (PRD F4)
    line: int               # 1-based, per docs/error-recovery.md §8
    column: int             # 1-based
    found: str              # offending text; "EOF" for the EOF token
    expected: list[str]     # what the failing expect() required; [] if not applicable
    snippet: str            # see below
    root_id: str            # == id until F2 (milestone 2) assigns clusters
    rule_ref: str           # catalog rule_ref; for "<production>" rows, the grammar rule being parsed
    # additions (docs/error-recovery.md §2)
    language: str           # always "c"
    caused_by: str | None   # set only by rules R1..R8 (+ plan 004 amendments)
    span_end: Position      # inclusive end, per §8
    message: str            # catalog template with placeholders filled

    def to_dict(self) -> dict: ...   # JSON-ready; span_end -> {"line", "column"}
```

```python
# catalog.py
@dataclass(frozen=True)
class CatalogEntry:
    code: str; phase: str; severity: str; category: str
    rule_ref: str          # without backticks; "<production>" for dynamic syntax refs
    message_template: str

def load_catalog(path: Path | None = None) -> dict[str, CatalogEntry]: ...
def load_grammar_rules(path: Path | None = None) -> frozenset[str]: ...   # the 36 rule names of language-spec §2 ebnf block; used to validate syntax rule_refs (added in review of plan 005)
    # default path: <repo root>/docs/error-catalog.md, where repo root = Path(__file__).resolve().parents[2]
    # parse table rows matching r"^\|\s*(LEX|SYN|SEM|WRN)-", 7 cells, strip backticks; cached (functools.lru_cache)
```

```python
# diagnostics.py
class ErrorSink:
    def __init__(self, source: str, catalog: dict[str, CatalogEntry] | None = None): ...
    def report(self, code: str, line: int, column: int, *,
               found: str,
               expected: Sequence[str] = (),
               span_end: Position | None = None,     # default: zero-width Position(line, column) if found == "EOF" or code == "SYN-MISSING-SEMICOLON";
                                                     #          otherwise Position(line, column + max(len(found),1) - 1)
               caused_by: str | None = None,
               rule_ref: str | None = None,          # required when the catalog rule_ref is "<production>"
               **message_args: object) -> ErrorRecord: ...
    @property
    def records(self) -> list[ErrorRecord]: ...      # creation order
    def summary(self) -> str: ...                    # PRD F4: "2 fatal, 3 warnings" (singular "1 fatal", "1 warning")
```

`report()` rules:
- `phase`, `severity` and the default `rule_ref` come from the catalog. If the catalog's `rule_ref` is `<production>`, a `rule_ref` argument is required, and it must be a grammar rule name.
- `id` is `f"E-{n:04d}"` in creation order. `root_id` is set to `id`. `language` is set to `"c"`.
- `snippet` is the source lines `max(1, line-1) .. min(last, line+1)`, joined with `"\n"` and otherwise unmodified. That gives "3 lines around the error" (PRD), or fewer at the file's edges.
- `message` is the template formatted with `found`, `expected` and the `message_args`. `{expected}` renders as the items joined by `" or "`. **Only for codes whose catalog phase is `syntax`**, each item is wrapped in single quotes, unless the template already writes `'{expected}'`. For lexical and semantic codes the items are inserted raw (they are type names, counts or names: "expects 2 argument(s)", not "expects '2' argument(s)"). `{found}` is always inserted raw (the templates already quote it where needed). Formatting is **strict**: a missing placeholder raises `KeyError`. That is a programming error and must surface in tests. *(Amended 2026-10-10 during review of plan 005.)*
- An unknown code raises `KeyError`.
- **`found` for type-valued templates.** For codes whose template uses `{found}` as a type name or count (SEM-TYPE-MISMATCH, SEM-ARG-COUNT, SEM-ARG-TYPE, SEM-RETURN-TYPE, SEM-INDEX-NOT-INT, WRN-IMPLICIT-NARROWING), `found` holds that type/count text, and the caller passes `span_end` explicitly (the offending identifier or operator's extent). *(Amended in review of plan 007.)*

## 3. Tokens and lexer (plan 005)

```python
# tokens.py
class TokenKind(Enum):
    IDENT; KEYWORD; UNSUPPORTED_KEYWORD; INT_LIT; FLOAT_LIT; CHAR_LIT; STRING_LIT
    OP; UNSUPPORTED_OP; PUNCT; EOF

TYPE_KEYWORDS = frozenset({"int", "float", "double", "char", "void"})

@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str               # exact source text ("EOF" for EOF)
    line: int; col: int     # start, 1-based
    end_line: int; end_col: int   # inclusive end; for EOF: the EOF position itself
    lex_gap: str | None = None    # docs/error-recovery.md §3
    value: object = None    # INT_LIT -> int, FLOAT_LIT -> float, CHAR_LIT -> str (1 char), STRING_LIT -> str (escapes decoded)
```

```python
# lexer.py
@dataclass
class LexResult:
    tokens: list[Token]                 # always ends with exactly one EOF token
    stdio_include: Position | None      # position of the '#' of the first accepted '#include <stdio.h>', else None

def lex(source: str, sink: ErrorSink) -> LexResult: ...
```

The EOF token's position is immediately after the last token (end line, end column + 1), or 1:1 for an empty file (error-recovery §8). Columns count characters, and a tab counts as one column. `

`, `
` and a lone `
` each count as one newline; `
` never occupies a column.

**Directives:** `#include <stdio.h>` is accepted when `#` is the first non-blank character of the line, with spaces or tabs allowed around the parts. It may be followed on the same line by whitespace and/or a comment (`// …`, or `/* … */` closed on that line), because comments are whitespace (language-spec §1). Anything else after it makes the line LEX-UNSUPPORTED-DIRECTIVE. *(Amended in review of plan 005.)*

## 4. AST (plan 006 defines it; plan 007 consumes it)

All nodes are `@dataclass`es in `src/cea/ast.py`. Every node has `span: Span`.

```python
@dataclass(frozen=True)
class Span:
    start_line: int; start_col: int; end_line: int; end_col: int   # inclusive, 1-based

# ---- top level
@dataclass
class Program:      decls: list["FunctionDecl | VarDeclStmt | ErrorStmt"]; span: Span   # span = 1:1 .. the EOF token's position (start = end = EOF pos); semantic uses span.end_* as the EOF position (amended in review of plan 007)

@dataclass
class Param:        type_name: str; name: str; name_pos: Position; span: Span

@dataclass
class FunctionDecl:
    ret_type: str; name: str; name_pos: Position
    params: list[Param]            # [] for both "()" and "(void)"
    body: "Block | None"           # None for a prototype
    span: Span
    error_id: str | None = None    # broken declaration (error-recovery §5)
    idents_in_span: set[str] = field(default_factory=set)

@dataclass
class VarDecl:                     # one declarator
    type_name: str; name: str; name_pos: Position
    array_size: "Expr | None"; init: "Expr | None"
    is_global: bool; span: Span
    error_id: str | None = None
    idents_in_span: set[str] = field(default_factory=set)

@dataclass
class VarDeclStmt:  decls: list[VarDecl]; span: Span       # "int a, b = 2;" (local or global)

# ---- statements
@dataclass
class Block:
    stmts: list["Stmt"]; span: Span
    orphan_of: str | None = None
    closed_by_repair: str | None = None

@dataclass
class If:           cond: "Expr"; then: "Stmt"; els: "Stmt | None"; span: Span
@dataclass
class While:        cond: "Expr"; body: "Stmt"; span: Span
@dataclass
class For:          init: "VarDeclStmt | Expr | None"; cond: "Expr | None"; step: "Expr | None"; body: "Stmt"; span: Span
@dataclass
class Return:       value: "Expr | None"; span: Span       # span starts at 'return'
@dataclass
class Break:        span: Span
@dataclass
class Continue:     span: Span
@dataclass
class ExprStmt:     expr: "Expr"; span: Span
@dataclass
class EmptyStmt:    span: Span

@dataclass
class ErrorStmt:                   # exactly the fields of error-recovery §5
    span: Span; error_id: str
    kind_hint: str                 # 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top' (+ 'unsupported', plan 004)
    declared_names: list[tuple[str, str]]
    idents_in_span: set[str]
    stopped_before: str | None

# ---- expressions
@dataclass
class IntLit:   value: int; span: Span
@dataclass
class FloatLit: value: float; span: Span
@dataclass
class CharLit:  value: str; span: Span
@dataclass
class StringLit: value: str; span: Span
@dataclass
class Name:     name: str; span: Span
@dataclass
class Unary:    op: str; operand: "Expr"; postfix: bool; span: Span   # '!', '-', '+', '++', '--'
@dataclass
class Binary:   op: str; left: "Expr"; right: "Expr"; op_pos: Position; span: Span
@dataclass
class Assign:   op: str; target: "Expr"; value: "Expr"; op_pos: Position; span: Span  # '=', '+=', ...
@dataclass
class Call:     callee: "Expr"; args: list["Expr"]; span: Span
@dataclass
class Index:    base: "Expr"; index: "Expr"; span: Span
@dataclass
class ErrorExpr: span: Span; error_id: str
```

```python
# parser.py
def parse(lex_result: LexResult, sink: ErrorSink) -> A.Program: ...
```

The parser never raises out of `parse()` on bad input. `ParseError` and `BlockRepair` (error-recovery §4.4, §4.7) are internal to `parser.py`.

## 5. Semantic analysis and pipeline (plan 007)

```python
# semantic.py
def analyze(program: A.Program, sink: ErrorSink, stdio_include: Position | None) -> None: ...

# pipeline.py
@dataclass
class CompileResult:
    errors: list[ErrorRecord]       # sink.records, creation order
    program: A.Program
    tokens: list[Token]
    @property
    def ok(self) -> bool: ...       # True iff no record has severity "fatal" (PRD F4: "a file with only warnings still compiles")
    def summary(self) -> str: ...   # delegates to ErrorSink.summary()

def compile_source(source: str, filename: str) -> CompileResult: ...
    # sink = ErrorSink(source); lr = lex(source, sink); prog = parse(lr, sink); analyze(prog, sink, lr.stdio_include)
    # never raises on any input; root_id stays == id (F2 is milestone 2)
```

## 6. Conventions every milestone-1 plan follows

- **Code style:** type hints everywhere; `@dataclass` for data; module docstring on every file; `snake_case` functions; no global mutable state except `lru_cache`d catalog loading; stdlib only.
- **Tests:**
  - Unit tests go in `tests/unit/test_<module>.py`. Use plain `assert`. Model them on `tests/test_corpus_schema.py`, which is the existing repo style: module docstring, small helpers, `pytest.mark.parametrize` for tables.
  - Run with `.venv/Scripts/python -m pytest`. Executors create `.venv` with `python -m venv .venv` and `.venv/Scripts/python -m pip install -r requirements-dev.txt` if it is missing; it is git-ignored.
- **Trace tests:** `tests/test_recovery_traces.py` (plan 007) asserts the exact record table of every trace T1–T7 in `docs/error-recovery.md` §9: id, code, line:col, found, caused_by. Plans 005 and 006 test the lexical and syntax subsets of those traces in their own unit tests.
- **Determinism:** no sets are iterated when creating records (sort first), and there is no dependence on dict order beyond insertion order.
- **Nothing may print** (see §1).
- **No changes to `docs/` or `tests/corpus/`** in plans 005–007. A needed spec change is reported, not made. Plan 004 is the only milestone-1 plan that edits docs and sidecars. **One advisor-approved exception:** plan 007 rewrites the `sem.return_paths` paragraph of `docs/language-spec.md` (a block returns on every path if ANY of its statements does; statements after it are unreachable), because the literal "last statement" wording made `return 1; f();` also warn about a missing return.
