# Plan 006: Build the milestone-1 parser with full error recovery (R1/R2/R9)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md`, unless a reviewer dispatched you and told you they
> maintain the index. End your final report with a **Viva notes** list: the
> decisions, trade-offs or deviations an examiner might ask about (see
> `plans/README.md`, "Viva notes convention"). Do not edit `VIVA.md`; the
> advisor folds your notes into it.
>
> Every code block marked **Listing** is the exact content to write. Copy it
> verbatim. Do not "improve" it, reformat it or add features. If a verification
> fails, the code you wrote differs from the plan, or the plan is wrong. Compare
> first, and STOP if the plan is wrong.
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 66fb191..HEAD -- src/cea/ast.py src/cea/parser.py 'tests/unit/test_parser*.py'` must print **nothing**.
> 2. `test -f src/cea/lexer.py && test -f src/cea/diagnostics.py && echo READY` must print `READY` (plan 005 has landed).
> 3. `grep -c 'R9' docs/error-recovery.md` must print a number **≥ 1** (plan 004 has landed; at `66fb191` it prints `7`).
> 4. `ls src/cea/ast.py src/cea/parser.py src/cea/pipeline.py 2>/dev/null | wc -l` must print `0`.
>
> If check 1 or 4 fails, someone has already started this work: STOP and report.
> If check 2 or 3 fails, a prerequisite plan has not landed: STOP and report.
> HEAD may be later than `66fb191` because of unrelated commits (for example to
> `plans/`). That is expected; only the paths in check 1 must be unchanged.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED (largest single module of milestone 1; every later phase and the AI layer read its records and AST)
- **Depends on**: `plans/004-amend-recovery-spec-corpus-gaps.md` (merged), `plans/005-m1-foundation-records-catalog-lexer.md` (merged). Plan 007 (semantic analyser, pipeline) runs **after** this plan.
- **Category**: direction (milestone 1, second of three plans: 005 → 006 → 007)
- **Planned at**: commit `66fb191`, 2026-10-10 (first drafted against `b0352b1`; `66fb191` contains the merged plans 004 and 005, the reviewed plan 007, and the contract amendments, including `Program.span`)

## Why this matters

The project is the "Compiler Error Assistant": a course compiler for a strict C99 subset, written in Python, that records every error as a structured record and links cascades through `caused_by`, so the UI can show one root cause per student mistake (PRD F2). Plan 005 built the records, the error interceptor (`ErrorSink`) and the lexer. This plan builds the **syntax phase**: a recursive-descent parser over `docs/language-spec.md` §2 that never stops at the first error, always returns a complete AST (with error nodes), picks the syntax error code by the catalog's selection rules 0–5, and links follow-on syntax errors to their cause by rules R2, R1 and R9. Plan 007's semantic analyser consumes this AST (its R3–R8 rules read the error nodes defined here), and the ten hand-traced examples of `docs/error-recovery.md` §9 only come out right if this parser reproduces their syntax records exactly. When this plan lands, every syntax-root dev corpus program reports its root, every valid program parses with zero records, and the syntax records of traces T1–T9 match the reference tables.

## Current state

- Repo: `C:\Users\Naman\OneDrive\Desktop\Compiler project`, branch `main`, HEAD `66fb191`, no remote. Windows 11, Git Bash, Python 3.13.1 as `python`.
- `src/cea/` (from plan 005) holds `__init__.py`, `catalog.py`, `diagnostics.py`, `lexer.py`, `records.py`, `tokens.py`. **There is no `ast.py`, `parser.py`, `semantic.py` or `pipeline.py`.**
- `tests/unit/` (from plan 005) holds `test_catalog.py`, `test_diagnostics.py`, `test_lexer.py`, `test_no_print.py`, `test_records.py`, `test_tokens.py`. `test_no_print.py` greps every `src/cea/*.py` for `print(`; the parser must never print.
- `pyproject.toml` sets `pythonpath = ["src"]`, `testpaths = ["tests"]` and `addopts = "-m 'not heldout'"`. pytest lives in `.venv/` (git-ignored; Step 0 creates it if missing). There is no `tests/__init__.py`; test modules are imported by basename, so do **not** create `tests/unit/__init__.py` or a `conftest.py`.
- The corpus `.c` files are checked out with CRLF line endings (`core.autocrlf=true`). The tests read them with `read_text()` (universal newlines); the plan-005 lexer also accepts `\r\n`.
- Baseline at `66fb191`: `.venv/Scripts/python -m pytest -q` → `358 passed, 1 skipped` (the skip is `tests/test_corpus_compile.py`, which waits for `cea.pipeline`, created by plan 007).

### The plan-005 interfaces this parser uses (contract `plans/m1-architecture.md` §2–§3, amended)

```python
# cea.records
@dataclass(frozen=True)
class Position: line: int; column: int

# cea.tokens
class TokenKind(Enum): IDENT; KEYWORD; UNSUPPORTED_KEYWORD; INT_LIT; FLOAT_LIT; CHAR_LIT; STRING_LIT; OP; UNSUPPORTED_OP; PUNCT; EOF
TYPE_KEYWORDS = frozenset({"int", "float", "double", "char", "void"})
@dataclass(frozen=True)
class Token:
    kind: TokenKind; text: str; line: int; col: int; end_line: int; end_col: int
    lex_gap: str | None = None; value: object = None   # INT_LIT->int, FLOAT_LIT->float, CHAR_LIT->str, STRING_LIT->str

# cea.lexer
@dataclass
class LexResult: tokens: list[Token]; stdio_include: Position | None   # tokens always end with exactly one EOF
def lex(source: str, sink: ErrorSink) -> LexResult: ...

# cea.diagnostics
class ErrorSink:
    def __init__(self, source: str, catalog=None): ...
    def report(self, code, line, column, *, found, expected=(), span_end=None, caused_by=None,
               rule_ref=None, **message_args) -> ErrorRecord: ...
    records: list[ErrorRecord]   # property, creation order
```

Contract facts that matter here (quoted from `plans/m1-architecture.md` §2–§3):

> If the catalog's `rule_ref` is `<production>`, a `rule_ref` argument is required, and it must be a grammar rule name.

> `span_end: Position | None = None,     # default: zero-width Position(line, column) if found == "EOF" or code == "SYN-MISSING-SEMICOLON"; otherwise Position(line, column + max(len(found),1) - 1)`

> `{expected}` renders as the items joined by `" or "`. **Only for codes whose catalog phase is `syntax`**, each item is wrapped in single quotes, unless the template already writes `'{expected}'`. … Formatting is **strict**: a missing placeholder raises `KeyError`.

> The EOF token's position is immediately after the last token (end line, end column + 1), or 1:1 for an empty file.

Plan 005's `report()` raises `ValueError` for a `rule_ref` that is not one of the 36 rule names of the language-spec §2 `ebnf` block (`cea.catalog.load_grammar_rules()`), and `TypeError` if `expected` is a bare `str`. This parser always passes a list, and passes `rule_ref` only for `<production>` codes. It always passes `span_end` explicitly.

### The AST you must define (contract §4, verbatim field lists; Step 1 implements it)

> All nodes are `@dataclass`es in `src/cea/ast.py`. Every node has `span: Span`.
> `Span(start_line, start_col, end_line, end_col)` (frozen, inclusive, 1-based) · `Program(decls, span)` — **span = 1:1 .. the EOF token's position; semantic uses span.end_* as the EOF position (amended in review of plan 007)** · `Param(type_name, name, name_pos, span)` · `FunctionDecl(ret_type, name, name_pos, params, body, span, error_id=None, idents_in_span=set())` — params `[]` for both `()` and `(void)`, body `None` for a prototype · `VarDecl(type_name, name, name_pos, array_size, init, is_global, span, error_id=None, idents_in_span=set())` (one declarator) · `VarDeclStmt(decls, span)` · `Block(stmts, span, orphan_of=None, closed_by_repair=None)` · `If(cond, then, els, span)` · `While(cond, body, span)` · `For(init, cond, step, body, span)` · `Return(value, span)` (span starts at `return`) · `Break(span)` · `Continue(span)` · `ExprStmt(expr, span)` · `EmptyStmt(span)` · `ErrorStmt(span, error_id, kind_hint, declared_names, idents_in_span, stopped_before)` · `IntLit/FloatLit/CharLit/StringLit(value, span)` · `Name(name, span)` · `Unary(op, operand, postfix, span)` · `Binary(op, left, right, op_pos, span)` · `Assign(op, target, value, op_pos, span)` · `Call(callee, args, span)` · `Index(base, index, span)` · `ErrorExpr(span, error_id)`.
>
> `def parse(lex_result: LexResult, sink: ErrorSink) -> A.Program` — "The parser never raises out of `parse()` on bad input. `ParseError` and `BlockRepair` are internal to `parser.py`." Always import the module as `from cea import ast as A`.

### The grammar (`docs/language-spec.md` §2, verbatim; each rule name is a runtime `rule_ref`)

> ```ebnf
> program        = { top_decl } , EOF ;
> top_decl       = type_spec , ( function_def | global_decl ) ;
> function_def   = IDENT , "(" , params , ")" , ( block | ";" ) ;
> params         = [ "void" | param_list ] ;
> param_list     = param , { "," , param } ;
> param          = type_spec , IDENT ;
> global_decl    = declarator , { "," , declarator } , ";" ;
> type_spec      = "int" | "float" | "double" | "char" | "void" ;
> declarator     = IDENT , [ array_suffix ] , [ "=" , expression ] ;
> array_suffix   = "[" , expression , "]" ;
> block          = "{" , { statement } , "}" ;
> statement      = var_decl | if_stmt | while_stmt | for_stmt | return_stmt
>                | break_stmt | continue_stmt | block | expr_stmt | empty_stmt ;
> var_decl       = var_core , ";" ;
> var_core       = type_spec , declarator , { "," , declarator } ;
> if_stmt        = "if" , "(" , expression , ")" , statement , [ "else" , statement ] ;
> while_stmt     = "while" , "(" , expression , ")" , statement ;
> for_stmt       = "for" , "(" , [ for_init ] , ";" , [ expression ] , ";"
>                , [ expression ] , ")" , statement ;
> for_init       = var_core | expression ;
> return_stmt    = "return" , [ expression ] , ";" ;
> break_stmt     = "break" , ";" ;
> continue_stmt  = "continue" , ";" ;
> expr_stmt      = expression , ";" ;
> empty_stmt     = ";" ;
> expression     = assignment ;
> assignment     = logic_or , [ assign_op , assignment ] ;
> assign_op      = "=" | "+=" | "-=" | "*=" | "/=" | "%=" ;
> logic_or       = logic_and , { "||" , logic_and } ;
> logic_and      = equality , { "&&" , equality } ;
> equality       = comparison , { ( "==" | "!=" ) , comparison } ;
> comparison     = term , { ( "<" | "<=" | ">" | ">=" ) , term } ;
> term           = factor , { ( "+" | "-" ) , factor } ;
> factor         = unary , { ( "*" | "/" | "%" ) , unary } ;
> unary          = ( "!" | "-" | "+" | "++" | "--" ) , unary | postfix ;
> postfix        = primary , { "(" , [ arg_list ] , ")" | "[" , expression , "]" }
>                , [ "++" | "--" ] ;
> arg_list       = assignment , { "," , assignment } ;
> primary        = INT_LIT | FLOAT_LIT | CHAR_LIT | STRING_LIT | IDENT
>                | "(" , expression , ")" ;
> ```
>
> - `top_decl` chooses `function_def` when the token after `IDENT` is `(`.
> - `params` is `void` alone only when the next token is `)`.
> - The left side of an `assign_op` and the operand of `++`/`--` must be an lvalue: `IDENT` or `IDENT[expression]`. Anything else is SYN-INVALID-ASSIGN-TARGET.
> - `else` binds to the nearest `if`.
> - A `*` directly after a `type_spec`, any UNSUPPORTED_KEYWORD and any UNSUPPORTED_OP are reported as SYN-UNSUPPORTED-FEATURE, naming the feature (pointers, structs, and so on).
> - These rule names are the `rule_ref` values for syntax errors.
>
> ## 3. Types
>
> - Integer types are `int` and `char`. Floating types are `float` and `double`. `void` is a return type only.
> - String literals have no usable type. Their only legal use is as the first argument of `printf`.
> - Usual arithmetic conversions: `char` becomes `int`. If either operand is `double`, the result is `double`. Otherwise, if either is `float`, the result is `float`. Otherwise it is `int`.
> - `%` and `%=` take integer operands only.
> - Comparison, equality, `&&`, `||` and `!` take arithmetic operands and produce `int`.
> - Assignment, initialisation, argument passing and return may convert any arithmetic type to any other. A floating value converted to an integer type gives the warning WRN-IMPLICIT-NARROWING.
> - Arrays are 1-D. Their element type is int, char, float or double. An array name is not a value: it cannot be assigned, returned or passed.
>
> ## 4. Semantic rules
>
> Each rule below has a statement and a C example that violates it.
>
> ### sem.declare_before_use
> Variables must be declared before use; lookup walks enclosing block scopes,
> then file scope. Functions must be declared (prototype or definition) earlier
> in the file than any call (C99 rule).
>
> ```c
> int main(void) {
>     y = 3;          /* y was never declared */
>     foo(1);         /* foo was never declared */
>     return 0;
> }
> ```
>
> ### sem.unique_in_scope
> A name may be declared once per scope; shadowing an outer scope is allowed.
> Parameters live in the function body's outermost scope; globals and functions
> share file scope. Defining a function body twice is a redeclaration.
>
> ```c
> int main(void) {
>     int x = 1;
>     int x = 2;      /* x is already declared in this scope */
>     return x;
> }
> ```
>
> ### sem.function_declarations
> A function may have several prototypes and one definition; all must agree on
> return type and parameter types.
>
> ```c
> int f(int a);
> float f(int a) {    /* return type disagrees with the prototype */
>     return 1.0;
> }
> ```
>
> ### sem.type_compat
> Operands, initialisers, assignments, arguments and returns must satisfy
> section 3.
>
> ```c
> int main(void) {
>     int x = "hi";       /* a string literal is not an arithmetic value */
>     int r = 7.5 % 2;    /* % needs integer operands */
>     return 0;
> }
> ```
>
> ### sem.no_void_values
> No variable or parameter may be void; a call to a void function cannot be
> used as a value.
>
> ```c
> void log_it(void) { }
> int main(void) {
>     int x = log_it();   /* log_it returns no value */
>     return 0;
> }
> ```
>
> ### sem.call_signature
> Only functions can be called, with exactly the declared number of arguments,
> each convertible to its parameter type.
>
> ```c
> int add(int a, int b) { return a + b; }
> int main(void) {
>     int x = 0;
>     x(1);               /* x is not a function */
>     return add(1);      /* add expects 2 arguments */
> }
> ```
>
> ### sem.return_type
> `return expr;` is only allowed in non-void functions and `expr` must convert
> to the return type; `return;` only in void functions (stricter than gcc, which
> warns).
>
> ```c
> void f(void) {
>     return 5;       /* void function returns a value */
> }
> int g(void) {
>     return;         /* non-void function returns nothing */
> }
> ```
>
> ### sem.return_paths
> A non-void function other than `main` should return on every path: the body's
> last statement is a `return`, or an `if` with an `else` whose branches both
> return on every path (recursively through blocks). Loops never count.
> Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly returns 0.
>
> ```c
> int f(int b) {
>     if (b) {
>         return 1;
>     }                   /* no return when b is 0 */
> }
> ```
>
> ### sem.array_access
> An array size must be an integer literal greater than 0 (no variable-length
> arrays). Only arrays may be indexed, and the index must have integer type.
> Constant out-of-range indices are not checked (runtime behaviour is out of scope).
>
> ```c
> int main(void) {
>     int n = 3;
>     int a[n];           /* size must be a literal */
>     int x = 1;
>     x[0] = 1;           /* x is not an array */
>     return 0;
> }
> ```
>
> ### sem.loop_control
> `break` and `continue` may appear only inside `while` or `for`.
>
> ```c
> int main(void) {
>     break;              /* not inside a loop */
>     return 0;
> }
> ```
>
> ### sem.global_init
> A global initialiser must be a numeric or char literal, optionally preceded
> by `-`.
>
> ```c
> int x = 4;
> int y = x + 1;          /* not a literal */
> ```
>
> ### sem.builtins
> `printf` is declared only if `#include <stdio.h>` appears before its first
> use. Its first argument must be a string literal; further arguments may be any
> arithmetic values. Format specifiers are not checked. Redeclaring `printf` is a
> redeclaration.
>
> ```c
> #include <stdio.h>
> int main(void) {
>     int x = 1;
>     printf(x);          /* first argument must be a string literal */
>     return 0;
> }
> ```
>
> ### sem.conditions
> Conditions of `if`, `while` and `for` must be arithmetic (any non-zero value
> is true). A plain `=` as the outermost operator of a condition produces a
> warning, as in gcc's -Wparentheses.
>
> ```c
> int main(void) {
>     int x = 0;
>     if (x = 5) {        /* assignment, probably meant == */
>         x = 1;
>     }
>     return x;
> }
> ```
>
> ### sem.entry_point
> The program must define `int main()` or `int main(void)`. Real C reports a
> missing main at link time; this compiler reports it at the end of semantic
> analysis.
>
> ```c
> void g(void) { }        /* the file has no main */
> ```
>
> ### sem.unused_declaration
> A local variable that is declared but never read produces a warning.
> Assigning with `=` is not a read. Compound assignment (`+=` and the like) and
> `++`/`--` both read and write. Parameters and globals are exempt.
>
> ```c
> int main(void) {
>     int t = 1;          /* t is never read */
>     return 0;
> }
> ```
>
> ### sem.unreachable
> The first statement after a `return`, `break` or `continue` in the same block
> produces one warning. This is a teaching warning that gcc does not emit.
>
> ```c
> int main(void) {
>     return 0;
>     return 1;           /* can never run */
> }
> ```
>
> ## 5. Example program
>
> Valid C99; expected: 0 fatal, 1 warning (WRN-IMPLICIT-NARROWING, at the line
> `int scaled = ratio * 2;`, where a double is converted to int).
>
> ```c
> #include <stdio.h>
>
> int total = 0;
>
> int square(int n);
>
> int square(int n) {
>     return n * n;
> }
>
> int main(void) {
>     int data[5];
>     int i;
>     char grade = 'A';
>     double ratio = 2.5;
>     int scaled = ratio * 2;
>
>     for (i = 0; i < 5; i++) {
>         data[i] = square(i);
>     }
>     i = 0;
>     while (i < 5) {
>         i++;
>         if (data[i - 1] % 2 == 0) {
>             continue;
>         } else {
>             total += data[i - 1];
>         }
>     }
>     {
>         int total = scaled;
>         printf("inner total: %d\n", total);
>     }
>     printf("grade %c, outer total %d\n", grade, total);
>     return 0;
> }
> ```
>
> ## 6. Not supported (deliberately)
>
> Each feature below is rejected with the message a student will see. All were
> cut for the same reason: the project is a one-semester effort, and each
> feature adds grammar, types or runtime concepts that are not needed to study
> compiler error handling.
>
> | Feature | Message the student sees | Why it was cut |
> |---|---|---|
> | Pointers (`int *p;`, address-of `&x`) | SYN-UNSUPPORTED-FEATURE: pointers are not supported in this course's C subset | Pointers alone would need a memory model and a larger type system. |
> | `struct`, `union`, `enum`, `typedef` | SYN-UNSUPPORTED-FEATURE: structs (unions, enums, typedef) are not supported in this course's C subset | User-defined types need type tables and member access rules. |
> | `switch`, `case`, `default`, `do`, `goto` | SYN-UNSUPPORTED-FEATURE: switch (do-while, goto) is not supported in this course's C subset | `if`, `while` and `for` already cover the control-flow error classes. |
> | `sizeof` | SYN-UNSUPPORTED-FEATURE: sizeof is not supported in this course's C subset | Needs type sizes and a type-expression grammar. |
> | `long`, `short`, `unsigned`, `signed` | SYN-UNSUPPORTED-FEATURE: integer type modifiers are not supported in this course's C subset | Multiplies the conversion rules without adding new error kinds. |
> | `const`, `static`, `extern`, `auto`, `register`, `volatile` | SYN-UNSUPPORTED-FEATURE: storage classes and qualifiers are not supported in this course's C subset | Needs linkage and const-correctness rules. |
> | Bitwise operators (and, or, xor, not, shifts), ternary `? :`, `.` and `->` | SYN-UNSUPPORTED-FEATURE: this operator is not supported in this course's C subset | More precedence levels and member access; little extra teaching value. |
> | Array initialiser lists, array parameters | SYN-UNSUPPORTED-FEATURE or SYN-EXPECTED-TOKEN at the `{` or `[` | Need initialiser typing and array-to-pointer decay. |
> | `scanf` and any header other than `<stdio.h>` | SEM-UNDECLARED-FUNC for `scanf` (its `&x` argument is already SYN-UNSUPPORTED-FEATURE) | Input needs pointers, which are unsupported. |
> | Preprocessor directives other than `#include <stdio.h>` (`#define`, `#if`, and so on) | LEX-UNSUPPORTED-DIRECTIVE: Only '#include <stdio.h>' is supported | A preprocessor is a separate language and a separate project. |

### Syntax-code selection (`docs/error-catalog.md`, verbatim)

| Code | rule_ref | Message template | Example trigger |
|---|---|---|---|
| SYN-MISSING-SEMICOLON | `<production>` | Expected ';' after {context} but found '{found}' | `int x = 5` then next line |
| SYN-UNBALANCED-BRACKET | `<production>` | Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}' | `if (x > 1 { }` |
| SYN-EXPECTED-TOKEN | `<production>` | Expected {expected} but found '{found}' | `while x > 1) { }` |
| SYN-EXPECTED-EXPRESSION | `<production>` | Expected an expression but found '{found}' | `int x = ;` |
| SYN-EXPECTED-TYPE | `<production>` | Expected a type (int, float, double, char, void) but found '{found}' | `int f(a) { }` |
| SYN-UNEXPECTED-EOF | `<production>` | File ended inside {context}; expected {expected} | `int main() { return 0;` |
| SYN-INVALID-ASSIGN-TARGET | `assignment` | Only a variable or array element can be assigned or incremented | `5 = x;` |
| SYN-UNSUPPORTED-FEATURE | `<production>` | {feature} is not supported in this course's C subset | `int *p;` |

> These rules are applied in order when the parser reports an error:
> 0. The found token is an UNSUPPORTED_KEYWORD or UNSUPPORTED_OP, or is `*` directly after a `type_spec` → `SYN-UNSUPPORTED-FEATURE`.
> 1. The found token is EOF → `SYN-UNEXPECTED-EOF`.
> 2. The expected set is exactly `;` → `SYN-MISSING-SEMICOLON`.
> 3. The expected set contains only closing brackets (`)`, `]`, `}`), or the found token is a closing bracket with no matching opener → `SYN-UNBALANCED-BRACKET`.
> 4. The parser expected the start of an expression → `SYN-EXPECTED-EXPRESSION`. It expected a type → `SYN-EXPECTED-TYPE`.
> 5. Otherwise → `SYN-EXPECTED-TOKEN`.

### Recovery rules (`docs/error-recovery.md`, amended by plan 004; verbatim excerpts)

**§4.1 Expected sets.** "The `expected` field, and the syntax-code selection rules in the catalog, use the token or token class that the failing `expect(...)` call required at that point (for example `[";"]` after a complete declarator). They do not use the full set of tokens that could legally follow." "The bracket stack used by selection rule 3 … contains only opening brackets **consumed by successful matches**. Brackets skipped during panic mode are never pushed." "**Optional constructs.** Where the grammar has an optional part (`[ arg_list ]` in a call, `[ expression ]` in `return_stmt`, the optional parts of a `for` header, `params`), the parser decides with one token of lookahead. If the current token is the token that ends the construct (`)` for a call or parameter list, `;` for `return` and the `for` header parts), the optional part is absent. Otherwise the parser **commits** to the optional part, and a failure inside it is reported with that part's expected set."

**§4.2 Missing semicolon.** "In `expect(";")`, if the current token is not `;`, is not EOF, and its start line is greater than the end line of the previous consumed token, then: record SYN-MISSING-SEMICOLON at the position immediately after the previous token (`line` = previous token's end line, `column` = previous token's end column + 1), with `found` = the current token's text and `expected = [";"]`. Consume nothing, return as if `;` had been matched, and do not enter panic mode or open an uncertain region." "When the found token is on the **same** line, the code is still SYN-MISSING-SEMICOLON … at the same 'after the previous token' location, but recovery is panic mode (§4.4). When the found token is EOF, the code is SYN-UNEXPECTED-EOF … and the EOF rule of §4.4 applies." "The repair is applied at every `;` site of the grammar, including the two `;` inside a `for` header."

**§4.3 Missing `)` before `{`.** "In `expect(")")`, if the current token is `{` and the required `)` is the one that closes the header of an `if`, `while` or `for` statement, then: record SYN-UNBALANCED-BRACKET at the `{` …, with `found = "{"` and `expected = [")"]`. The message names the `(` that opened the header and its line. Consume nothing, return as if `)` had been matched, and do not enter panic mode or open an uncertain region."

**§4.4 Panic mode and sync sets.**
```text
SYNC_STMT_CONSUME = { ";" }   -- skip up to and including the first ";"
SYNC_STMT_STOP    = { "}", "if", "while", "for", "return", "break", "continue", "{", "int", "float", "double", "char", "void", EOF }   -- stop BEFORE these; do not consume
SYNC_FOR_HEADER   = inside a for header: ";" is NOT a sync token; consume the ")" that closes the header; stop before SYNC_STMT_STOP
SYNC_BLOCK        = { "}" }   -- the block loop ends at "}" (consumed by the block's own expect) or EOF; panic never consumes "}"
SYNC_TOP_STOP     = a type keyword that is the first token on its line AND the depth of "{"/"}" skipped so far in this panic is 0; or EOF   -- stop before; do not consume
```
"Errors other than phrase repair raise an internal `ParseError(error_id)` after the record is created. Catch points: (a) `statement()`: … It catches, runs statement-level panic (or for-header panic if the error occurred between `for (` and the header's `)`), and returns an `ErrorStmt`. One exception: if the statement is a `var_decl` and its first declarator's `IDENT` has already been consumed, it returns the `VarDecl` instead, marked as a broken declaration (§5). (b) The declarator initializer `= expression` and the `array_suffix` expression in `var_decl` and `global_decl` (CP-INIT, CP-SIZE). These catch, replace the expression with an `ErrorExpr`, run panic (statement-level for locals, top-level for globals), and return the declaration node, which still declares its name. (c) `top_decl()`: it catches and runs top-level panic. It returns an `ErrorStmt` at top level (`kind_hint = "top"`)."
"**Statement-level panic.** Look at the current token. If it is in `SYNC_STMT_STOP`, stop. If it is `;`, consume it and stop. Otherwise consume it (skip) and repeat. When panic stops without having consumed a `;`, the `ErrorStmt` records `stopped_before` = the text of the token it stopped at."
"**For-header panic.** … Keep a parenthesis depth `d` = 1 + the number of `(` opened by successful matches inside the header and not yet closed. Skip tokens; `(` adds 1 to `d`, `)` subtracts 1. When `d` reaches 0, consume that `)` and stop; the next token (normally the start of the body) is then recorded as `stopped_before`. Stop earlier, before the token and without consuming it, if the current token is in `SYNC_STMT_STOP`. A `;` is just skipped."
"**Top-level panic.** Skip tokens, tracking `{` (+1) and `}` (−1) among skipped tokens; the depth never goes below 0 … Stop before a `SYNC_TOP_STOP` token. 'First token on its line' means no other token starts earlier on the same line."
"**EOF.** Panic always stops at EOF. A block whose loop ends at EOF calls `expect("}")`, which records SYN-UNEXPECTED-EOF (`expected = ["}"]`, at the EOF position) and then **returns the block normally** without raising. … Each still-open block records its own SYN-UNEXPECTED-EOF. The 2nd and later ones are linked by rule R2." "**Errors inside the header of a function definition** (the parameter list) are caught by `top_decl()`."

**§4.5 Uncertain region.** "The parser keeps `recovering: error_id | None`. **Opened** when panic mode starts for error E (any level), or when an EOF error is recorded. If it is already open, its owner does not change. **Not opened** by phrase repair (§4.2, §4.7, and §4.3). **Closed** when (i) statement-level panic consumes a `;`, (ii) top-level panic stops at a SYNC_TOP_STOP type keyword, or (iii) any `;` or `}` is consumed by a successful match. While it is open, every new syntax error gets `caused_by = recovering` (rule R2)." Known limitation: "a for-header panic that ends by consuming the header's `)` does not close the region".

**§4.6 Progress guarantee.** Every `;` site (S1 prototype, S2 `global_decl`, S3 `var_decl`, S4/S5 the two `for` header `;`, S6 `return`, S7 `break`, S8 `continue`, S9 `expr_stmt`, S10 `empty_stmt`) follows at least one consumed token. "**Loop guard (safety net).** The block's statement loop and the program's `top_decl` loop record the token index before each iteration. If an iteration consumed nothing, they skip one token. In test mode they also raise an assertion, because by points 1–2 this must never happen."

**§4.7 Missing `}`.** "In `statement()`, before any other alternative: if the current token is a type keyword, the next token is `IDENT`, and the token after that is `(`, then record SYN-UNBALANCED-BRACKET at the type keyword, with `found` = the type keyword's text and `expected = ["}"]`. The message names the innermost open `{` and its line. Every open block of the current function is then closed without consuming anything. Each `Block` node is ended at the previous token and gets `closed_by_repair = <this error id>`. Control returns to the top-level `top_decl` loop. Only ONE record is created … No uncertain region is opened." "The repair is raised as an internal `BlockRepair(error_id)` exception that is *not* a `ParseError` … Each `block()` on the way catches it, ends itself at the previous token, sets `closed_by_repair`, and re-raises. `function_def` catches it after its body block and returns the function node normally. If an uncertain region is already open when the repair fires …, the new record is linked to that region by R2."

**§5 Error nodes.** `ErrorStmt.span` = "first token of the statement .. last token consumed or skipped"; `kind_hint` ∈ `'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top' 'unsupported'`; `declared_names` = "(name, type) for each `type_spec IDENT` consumed inside it; type is `"<unsupported>"` for names recovered from unsupported code"; `idents_in_span` = "every IDENT text inside span (consumed or skipped)"; `stopped_before` = "token text if panic stopped without consuming, else None". "`Block` gains `orphan_of`. It is set to the current `recovering` id when the block starts at a `{` where panic stopped (`stopped_before == "{"`)." Rules:
- "**Broken declaration.** Once `type_spec IDENT` of a local or global variable has been consumed, a later error never turns the declaration into an `ErrorStmt`. The node is kept, the name is declared with its declared type, a failed initializer or array size becomes an `ErrorExpr`, and remaining declarators after the error are lost."
- "A **function** whose header fails (error inside `params`) becomes a top-level `ErrorStmt` with `declared_names = [(name, "function")]`."
- "A `for` statement whose header failed after `for (int i` gives `declared_names = [("i","int")]`."
- "**`kind_hint = 'unsupported'`** is used when the statement (or top-level declaration) **starts** with an UNSUPPORTED_KEYWORD."
- "**Declarator-like names in unsupported code.** When an `ErrorStmt`'s error is SYN-UNSUPPORTED-FEATURE, `declared_names` additionally contains every IDENT in its span that (a) is immediately preceded by a type keyword, by `*`, or by another IDENT, and (b) is immediately followed by `=`, `;`, `,` or `[`. Each such name gets type `"<unsupported>"`, in source order without duplicates."

**§7 caused_by for syntax records.** "R1 lex gap — any syntax record — the found token's `lex_gap` is set and R2 does not apply — the `lex_gap` id." "R2 uncertain region — any syntax record — `recovering` is open when the record is created — `recovering`." "R9 orphan unsupported body — any syntax record — R2 and R1 do not apply, and the innermost `Block` being parsed has `orphan_of` = X, where X is an `ErrorStmt` with `kind_hint` `unsupported` — X's `error_id`." "Precedence: for syntax records, R2, then R1, then R9."

**§8 Locations.** "SYN-MISSING-SEMICOLON is reported at the line and column immediately after the last token of the unterminated statement. Every other syntax error is reported at the found token." EOF: `found = "EOF"`. `span_end`: "SYN-MISSING-SEMICOLON and EOF errors = same as `(line, column)`; other syntax = last character of the found token".

### Interpretation decisions this plan makes (the code below implements exactly these)

The spec leaves these points open. Each is mechanical and is tested. If a reviewer disagrees, change the decision in a follow-up plan, not during execution.

- **D1 Expected-set classes.** Besides literal token texts, `expected` uses three class names: `"expression"` (catalog rule 4, SYN-EXPECTED-EXPRESSION), `"type"` (rule 4, SYN-EXPECTED-TYPE) and `"identifier"` (falls to rule 5, so `int 5;` gives "Expected 'identifier' but found '5'").
- **D2 Comma lists.** After a parameter or a call argument the parser requires `,` or `)`: `expected = [",", ")"]`. That set is not "only closing brackets", so rule 5 gives SYN-EXPECTED-TOKEN. Consequence (required by the advisor, catalog followed literally): an array parameter `int f(int a[])` is SYN-EXPECTED-TOKEN at `[`, and an array initialiser `int a[3] = {1, 2};` is SYN-EXPECTED-EXPRESSION at `{` (then the orphan block's `1, 2` gives a linked SYN-MISSING-SEMICOLON). Neither is special-cased. A declarator list keeps `[";"]` (§4.1 says so explicitly).
- **D3 §4.2 wins over rule 0 on a later line.** `x = 1` followed on the next line by `switch (x)` gives SYN-MISSING-SEMICOLON (the §4.2 repair, as its text prescribes), then `switch` is reported by its own statement. On the same line, rule 0 applies (`x = a & b;` gives SYN-UNSUPPORTED-FEATURE at `&`).
- **D4 rule_ref** is the name of the innermost grammar-rule method currently executing (a decorator pushes it). An unsupported keyword at the start of a statement is reported by `statement()` itself (`rule_ref = "statement"`, `expected = []`), as trace T8 requires.
- **D5 SYN-INVALID-ASSIGN-TARGET** is reported at the assignment or `++`/`--` operator (`found` = the operator text, `expected = []`), checked before the operator is consumed (for a prefix `++`/`--`, after its operand is parsed). It raises `ParseError`, so the statement becomes an `ErrorStmt`. A parenthesised name `(x)` is not `IDENT` and is rejected (stricter than gcc).
- **D6 CP-INIT/CP-SIZE** are implemented as "store an `ErrorExpr` on the declarator, then re-raise". The enclosing `statement()`/`top_decl()` runs the panic (statement-level locally, top-level for globals) and returns the broken declaration. The observable result is the one §4.4(b) describes. Inside a `for` header the same error makes the whole `for` an `ErrorStmt` (a `for_init` is not a `var_decl`).
- **D7 Multi-declarator broken declarations.** Only the **last** declarator (the one being parsed when the error happened) gets `error_id`; its `idents_in_span` covers its own name token through the last skipped token (T1b: `{b, a}`). Earlier, complete declarators stay normal.
- **D8 Failed function header** (error between the `(` and the `)` of the parameter list): `ErrorStmt(kind_hint="top", declared_names=[(name, "function")] + any plan-004 "<unsupported>" names)`. Parameters are not added (their uses are in the skipped body; adding them would let R5 link unrelated uses in later functions).
- **D9 Error after a complete header** (e.g. `int f(void) x`): a broken `FunctionDecl` (`error_id` set, `body = None`), then top-level panic.
- **D10 BlockRepair keeps statements.** `if`/`while`/`for` catch `BlockRepair`, rebuild themselves around the closed block (`r.node`) and re-raise, so a missing `}` inside nested statements loses no nodes. Only blocks set `closed_by_repair`.
- **D11 Bracket stack discipline.** Every catch point and every `block()` truncates the stack to its depth on entry, so openers of a failed statement never leak (a later stray `)` is then correctly "with no matching opener").
- **D12 Message arguments.** `{context}` comes from a rule→phrase table (`var_decl` → "the declaration", `block` → "the block", expression rules → "the expression", …). `{opener}`/`{open_line}` name the innermost matched opener of the expected closer. For rule 3's second clause (a stray closer, no opener exists), they are `opener` = the closer's mirror and `open_line = "?"` (the catalog template assumes an opener; see Maintenance notes). `{feature}` is `'switch'`-style for keywords, `The operator '&'` for operators and `A pointer ('*' after a type)` for `*`.
- **D13 Recursion.** Each expression nesting level costs about 30 Python frames, so `parse()` raises the recursion limit to 20 000 for its own duration and restores it (200 nested parentheses parse; the default limit fails at about 35).
- **D14 `Program.span`** is `Span(1, 1, eof.line, eof.col)` (contract amendment).
- **D15 `orphan_of`** is set when a block starts at the token index where the last panic stopped (statement-level or for-header panic), to the current `recovering` id.

## Commands you will need

| Purpose | Command (project root, Git Bash) | Expected on success |
|---|---|---|
| Create venv (only if `.venv/` is missing) | `python -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt` | exit 0 |
| Parser tests so far | `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` | `N passed` (N per step) |
| Full suite | `.venv/Scripts/python -m pytest -q` | `358 passed, 1 skipped` before; `591 passed, 1 skipped` after |
| Leftover stubs | `grep -c NotImplementedError src/cea/parser.py` | `0` after Step 9 |
| No prints | `grep -n 'print(' src/cea/ast.py src/cea/parser.py` | no output |

`tests/unit/test_parser_*.py` is a shell glob, so it runs exactly the parser test files created so far.

## Scope

**In scope** (create only these; modify nothing else except the `plans/README.md` status row):
- `src/cea/ast.py` (create)
- `src/cea/parser.py` (create)
- `tests/unit/test_parser_ast.py`, `test_parser_core.py`, `test_parser_grammar.py`, `test_parser_repairs.py`, `test_parser_panic.py`, `test_parser_region.py`, `test_parser_error_nodes.py`, `test_parser_progress.py`, `test_parser_lvalue.py`, `test_parser_traces.py`, `test_parser_corpus.py` (create, all in `tests/unit/`)

**Out of scope** (do NOT touch):
- `src/cea/pipeline.py`, `semantic.py`, `cli.py`, `__main__.py`: plan 007 owns them. Creating `pipeline.py` would switch on `tests/test_corpus_compile.py` before the analyser exists and turn the suite red.
- Every plan-005 file (`src/cea/{__init__,catalog,diagnostics,lexer,records,tokens}.py`, `tests/unit/test_{catalog,diagnostics,lexer,no_print,records,tokens}.py`). If one seems wrong, STOP and report.
- `docs/`, `tests/corpus/`, `tools/`, `pyproject.toml`, `requirements-dev.txt`, `VIVA.md`, the existing `tests/*.py`. A needed spec change is reported, not made (contract §6).
- `tests/corpus/heldout/`: never read it, never point a test at it (corpus README §5, held-out rule).

## Git workflow

- Branch: `advisor/006-m1-parser`, created from `main` (`git switch -c advisor/006-m1-parser`). If a reviewer runs you in an isolated worktree, commit on the worktree's branch instead.
- One commit per step that changes files (Steps 1–11), staged by explicit path (never `git add -A` or `git add .`). Message style follows the repo (`git log`: `cea: add lexer for tokens and literals (plan 005 step 4)`): `cea: <what> (plan 006 step N)`, then a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use two `-m` flags, for example:
  `git commit -m "cea: add AST node dataclasses (plan 006 step 1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`
- Do not push, merge or open a PR.

## Steps

### Step 0: Baseline

1. Run the drift check at the top of this plan.
2. `git switch -c advisor/006-m1-parser`
3. If `.venv/Scripts/python` does not exist: `python -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt`.
4. `.venv/Scripts/python -m pytest -q`

**Verify**: the last line is `358 passed, 1 skipped in …`. Call this number B (= 358). If it differs, or anything fails, STOP. No commit.

### Step 1: The AST module

Create `src/cea/ast.py` with exactly Listing 1, and `tests/unit/test_parser_ast.py` with exactly Listing T1.

**Listing 1 — `src/cea/ast.py`**

```python
"""AST node dataclasses for the course C subset.

Defined by plans/m1-architecture.md section 4 (plan 006); consumed by the
semantic analyser (plan 007). The error nodes and recovery fields follow
docs/error-recovery.md section 5. Import this module as
``from cea import ast as A`` so it never shadows the standard-library ``ast``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from cea.records import Position


@dataclass(frozen=True)
class Span:
    """Inclusive, 1-based source range."""
    start_line: int
    start_col: int
    end_line: int
    end_col: int


# ---- top level
@dataclass
class Program:
    decls: list["FunctionDecl | VarDeclStmt | ErrorStmt"]
    span: Span


@dataclass
class Param:
    type_name: str
    name: str
    name_pos: Position
    span: Span


@dataclass
class FunctionDecl:
    ret_type: str
    name: str
    name_pos: Position
    params: list[Param]            # [] for both "()" and "(void)"
    body: "Block | None"           # None for a prototype
    span: Span
    error_id: str | None = None    # broken declaration (error-recovery section 5)
    idents_in_span: set[str] = field(default_factory=set)


@dataclass
class VarDecl:
    """One declarator."""
    type_name: str
    name: str
    name_pos: Position
    array_size: "Expr | None"
    init: "Expr | None"
    is_global: bool
    span: Span
    error_id: str | None = None
    idents_in_span: set[str] = field(default_factory=set)


@dataclass
class VarDeclStmt:
    """'int a, b = 2;' (local or global)."""
    decls: list[VarDecl]
    span: Span


# ---- statements
@dataclass
class Block:
    stmts: list["Stmt"]
    span: Span
    orphan_of: str | None = None
    closed_by_repair: str | None = None


@dataclass
class If:
    cond: "Expr"
    then: "Stmt"
    els: "Stmt | None"
    span: Span


@dataclass
class While:
    cond: "Expr"
    body: "Stmt"
    span: Span


@dataclass
class For:
    init: "VarDeclStmt | Expr | None"
    cond: "Expr | None"
    step: "Expr | None"
    body: "Stmt"
    span: Span


@dataclass
class Return:
    value: "Expr | None"
    span: Span                     # starts at 'return'


@dataclass
class Break:
    span: Span


@dataclass
class Continue:
    span: Span


@dataclass
class ExprStmt:
    expr: "Expr"
    span: Span


@dataclass
class EmptyStmt:
    span: Span


@dataclass
class ErrorStmt:
    """A statement or top-level declaration that failed and was skipped."""
    span: Span
    error_id: str
    kind_hint: str   # 'if' 'while' 'for' 'return' 'break' 'continue' 'decl' 'expr' 'top' 'unsupported'
    declared_names: list[tuple[str, str]]
    idents_in_span: set[str]
    stopped_before: str | None


# ---- expressions
@dataclass
class IntLit:
    value: int
    span: Span


@dataclass
class FloatLit:
    value: float
    span: Span


@dataclass
class CharLit:
    value: str
    span: Span


@dataclass
class StringLit:
    value: str
    span: Span


@dataclass
class Name:
    name: str
    span: Span


@dataclass
class Unary:
    op: str                        # '!', '-', '+', '++', '--'
    operand: "Expr"
    postfix: bool
    span: Span


@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    op_pos: Position
    span: Span


@dataclass
class Assign:
    op: str                        # '=', '+=', '-=', '*=', '/=', '%='
    target: "Expr"
    value: "Expr"
    op_pos: Position
    span: Span


@dataclass
class Call:
    callee: "Expr"
    args: list["Expr"]
    span: Span


@dataclass
class Index:
    base: "Expr"
    index: "Expr"
    span: Span


@dataclass
class ErrorExpr:
    """Stands in for an expression that failed to parse (type <error>)."""
    span: Span
    error_id: str


Expr = Union[IntLit, FloatLit, CharLit, StringLit, Name, Unary, Binary, Assign, Call, Index, ErrorExpr]
Stmt = Union[VarDeclStmt, Block, If, While, For, Return, Break, Continue, ExprStmt, EmptyStmt, ErrorStmt]
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `30 passed`
- `.venv/Scripts/python -c "import sys; sys.path.insert(0, 'src'); import ast; from cea import ast as A; print(ast.parse('1').__class__.__name__, A.__name__)"` → `Module cea.ast`
- Commit `src/cea/ast.py tests/unit/test_parser_ast.py`: `cea: add AST node dataclasses (plan 006 step 1)`

### Step 2: Parser core — cursor, `expect()`, code selection, bracket stack, caused_by, rule_ref

Create `src/cea/parser.py` with exactly Listing 2, and `tests/unit/test_parser_core.py` with exactly Listing T2. Listing 2 is a complete, importable module: constants, the internal exceptions, the `rule` decorator (it pushes the grammar rule name that becomes `rule_ref`), `parse()` (which calls `program()`, added in Step 3), and the core methods of `Parser`:
- the token cursor (`cur`, `peek`, `prev`, `at`, `consume`);
- `match()` (pushes/pops the bracket stack, closes the uncertain region on `;`/`}`: §4.5 (iii));
- `expect()`/`expect_ident()`;
- `select_code()` (catalog rules 0–5, in order);
- `caused_by()` (R2, then R1, then R9);
- `message_args()`, `report()` (the only call into `ErrorSink`; an EOF record opens the region) and `fail()` (report, then raise `ParseError`).

**Listing 2 — `src/cea/parser.py` (complete file after this step)**

```python
"""Recursive-descent parser for the course C subset, with error recovery.

Grammar: docs/language-spec.md section 2 (each method below is named after the
EBNF rule it parses; that name is the runtime ``rule_ref`` of a syntax record).
Recovery: docs/error-recovery.md sections 4 and 5 (as amended by plan 004):
phrase repairs (4.2 missing ';', 4.3 missing ')' before '{', 4.7 missing '}'),
panic mode with sync sets (4.4), the uncertain region (4.5), the progress
guarantee (4.6), error nodes and broken declarations (5), and the caused_by
rules for syntax records: R2, then R1, then R9 (7).
Code selection: docs/error-catalog.md, "Choosing among syntax codes", rules 0-5.

The only public entry point is ``parse()``. ``ParseError``, ``BlockRepair`` and
``Parser`` are internal. Nothing here prints.
"""
from __future__ import annotations

import functools
import sys
from dataclasses import dataclass
from typing import Callable, NoReturn, TypeVar

from cea import ast as A
from cea.diagnostics import ErrorSink
from cea.lexer import LexResult
from cea.records import Position
from cea.tokens import TYPE_KEYWORDS, Token, TokenKind

# Each nesting level of an expression costs about 30 Python frames (11 rule methods
# plus their decorator wrappers), so parse() raises the recursion limit to this
# value for its own duration (restored afterwards).
RECURSION_LIMIT = 20_000

# Tests set this to True: the loop guard (error-recovery 4.6 point 3) then raises
# ProgressError instead of silently skipping a token.
STRICT_PROGRESS = False

K = TokenKind
SYMBOLIC = (K.KEYWORD, K.OP, K.PUNCT)
EXPR = "expression"      # expected-set class: the start of an expression (catalog rule 4)
TYPE = "type"            # expected-set class: a type_spec (catalog rule 4)
IDENT = "identifier"     # expected-set class: an IDENT (falls to catalog rule 5)
ASSIGN_OPS = ("=", "+=", "-=", "*=", "/=", "%=")
OPENER_OF = {")": "(", "]": "[", "}": "{"}
STMT_KEYWORDS = ("if", "while", "for", "return", "break", "continue")
SYNC_STMT_STOP = frozenset({"}", "{", *STMT_KEYWORDS, *TYPE_KEYWORDS})   # plus EOF (checked by kind)
# Codes whose catalog rule_ref is "<production>": the parser passes the current grammar rule.
PRODUCTION_CODES = frozenset({
    "SYN-MISSING-SEMICOLON", "SYN-UNBALANCED-BRACKET", "SYN-EXPECTED-TOKEN",
    "SYN-EXPECTED-EXPRESSION", "SYN-EXPECTED-TYPE", "SYN-UNEXPECTED-EOF", "SYN-UNSUPPORTED-FEATURE",
})
# Noun phrases for the {context} placeholder of SYN-MISSING-SEMICOLON and SYN-UNEXPECTED-EOF.
RULE_PHRASES = {
    "program": "the program", "top_decl": "the declaration", "function_def": "the function declaration",
    "params": "the parameter list", "param_list": "the parameter list", "param": "the parameter",
    "global_decl": "the declaration", "type_spec": "the type", "declarator": "the declarator",
    "array_suffix": "the array size", "block": "the block", "statement": "the statement",
    "var_decl": "the declaration", "var_core": "the declaration", "if_stmt": "the if statement",
    "while_stmt": "the while loop", "for_stmt": "the for loop header", "for_init": "the for loop header",
    "return_stmt": "the return statement", "break_stmt": "the break statement",
    "continue_stmt": "the continue statement", "expr_stmt": "the expression statement",
}
EXPRESSION_RULES = ("expression", "assignment", "logic_or", "logic_and", "equality", "comparison",
                    "term", "factor", "unary", "postfix", "primary", "arg_list")


class ParseError(Exception):
    """Raised after a syntax record is created (error-recovery 4.4). Internal."""

    def __init__(self, error_id: str, code: str) -> None:
        super().__init__(error_id)
        self.error_id = error_id
        self.code = code
        self.in_for_header = False   # set by for_stmt: use for-header panic


class BlockRepair(Exception):
    """The 4.7 missing-'}' repair. Not a ParseError, so statement() does not catch it."""

    def __init__(self, error_id: str) -> None:
        super().__init__(error_id)
        self.error_id = error_id
        self.node: A.Stmt | None = None   # the innermost closed construct, handed outwards


class ProgressError(AssertionError):
    """Raised by the loop guard when STRICT_PROGRESS is True."""


@dataclass
class _TopCtx:
    """What top_decl() has consumed so far (for its catch point)."""
    func_name: Token | None = None
    func_name_index: int = -1
    func_node: A.FunctionDecl | None = None


F = TypeVar("F", bound=Callable)


def rule(name: str) -> Callable[[F], F]:
    """Decorator: push the grammar rule name while the method runs (runtime rule_ref)."""
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self: "Parser", *args, **kwargs):
            self.rules.append(name)
            try:
                return fn(self, *args, **kwargs)
            finally:
                self.rules.pop()
        return wrapper  # type: ignore[return-value]
    return deco


def is_type_kw(tok: Token) -> bool:
    return tok.kind is K.KEYWORD and tok.text in TYPE_KEYWORDS


def parse(lex_result: LexResult, sink: ErrorSink) -> A.Program:
    """Parse the token stream; always returns a complete Program (never raises on bad input)."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, RECURSION_LIMIT))
    try:
        return Parser(lex_result.tokens, sink).program()
    finally:
        sys.setrecursionlimit(old)


class Parser:
    # ======================================================= core (step 2)
    def __init__(self, tokens: list[Token], sink: ErrorSink) -> None:
        self.toks = tokens
        self.pos = 0
        self.sink = sink
        self.rules: list[str] = []
        self.brackets: list[Token] = []          # openers consumed by successful matches (4.1)
        self.recovering: str | None = None       # uncertain-region owner (4.5)
        self.block_orphans: list[str | None] = []  # orphan_of of each Block being parsed (R9)
        self.unsupported_ids: set[str] = set()   # error ids of ErrorStmts with kind_hint 'unsupported'
        self.stop_index = -1                     # token index where the last panic stopped (orphan test)
        self.decl_log: list[tuple[int, str, str]] = []   # (IDENT index, name, type) of consumed declarators
        self.partial_decl: A.VarDeclStmt | None = None   # var_decl/global_decl being parsed
        self.name_index: dict[int, int] = {}     # id(VarDecl) -> its IDENT token index
        self.top_ctx = _TopCtx()
        self.paren: dict[int, A.Expr] = {}       # parenthesised expressions (not lvalues); keeps them alive

    @property
    def cur(self) -> Token:
        return self.toks[self.pos]

    def peek(self, k: int) -> Token:
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    @property
    def prev(self) -> Token:
        return self.toks[self.pos - 1]

    @staticmethod
    def is_(tok: Token, text: str) -> bool:
        return tok.kind in SYMBOLIC and tok.text == text

    def at(self, text: str) -> bool:
        return self.is_(self.cur, text)

    def at_any(self, texts: tuple[str, ...]) -> bool:
        return self.cur.kind in SYMBOLIC and self.cur.text in texts

    def consume(self) -> Token:
        """Advance one token without any bookkeeping (used for skipping and for keywords)."""
        tok = self.toks[self.pos]
        if tok.kind is not K.EOF:
            self.pos += 1
        return tok

    def match(self, text: str) -> Token:
        """Consume the current token, which the caller has checked is `text` (a successful match)."""
        tok = self.consume()
        if text in ("(", "[", "{"):
            self.brackets.append(tok)
        elif text in OPENER_OF and self.brackets and self.brackets[-1].text == OPENER_OF[text]:
            self.brackets.pop()
        if text in (";", "}"):
            self.recovering = None           # 4.5 (iii)
        return tok

    def expect(self, text: str) -> Token:
        if self.at(text):
            return self.match(text)
        self.fail([text])

    def expect_ident(self) -> Token:
        if self.cur.kind is K.IDENT:
            return self.consume()
        self.fail([IDENT])

    def span(self, i: int, j: int) -> A.Span:
        a, b = self.toks[i], self.toks[max(i, j)]
        return A.Span(a.line, a.col, b.end_line, b.end_col)

    @staticmethod
    def join(a: A.Span, b: A.Span) -> A.Span:
        return A.Span(a.start_line, a.start_col, b.end_line, b.end_col)

    def span_from(self, start: int) -> A.Span:
        """Span from token `start` to the last consumed token."""
        return self.span(start, self.pos - 1)

    def select_code(self, tok: Token, expected: list[str]) -> str:
        """Catalog "Choosing among syntax codes", rules 0-5, in order."""
        if tok.kind in (K.UNSUPPORTED_KEYWORD, K.UNSUPPORTED_OP) or (
                self.is_(tok, "*") and self.pos > 0 and is_type_kw(self.prev)):
            return "SYN-UNSUPPORTED-FEATURE"                                   # rule 0
        if tok.kind is K.EOF:
            return "SYN-UNEXPECTED-EOF"                                        # rule 1
        if expected == [";"]:
            return "SYN-MISSING-SEMICOLON"                                     # rule 2
        if (expected and all(e in OPENER_OF for e in expected)) or self.stray_closer(tok):
            return "SYN-UNBALANCED-BRACKET"                                    # rule 3
        if EXPR in expected:
            return "SYN-EXPECTED-EXPRESSION"                                   # rule 4
        if TYPE in expected:
            return "SYN-EXPECTED-TYPE"                                         # rule 4
        return "SYN-EXPECTED-TOKEN"                                            # rule 5

    def stray_closer(self, tok: Token) -> bool:
        return (tok.kind is K.PUNCT and tok.text in OPENER_OF
                and all(b.text != OPENER_OF[tok.text] for b in self.brackets))

    def caused_by(self, tok: Token) -> str | None:
        """R2, then R1, then R9 (error-recovery 7, amended by plan 004)."""
        if self.recovering is not None:
            return self.recovering                                             # R2
        if tok.lex_gap is not None:
            return tok.lex_gap                                                 # R1
        if self.block_orphans and self.block_orphans[-1] in self.unsupported_ids:
            return self.block_orphans[-1]                                      # R9
        return None

    def message_args(self, code: str, tok: Token, expected: list[str]) -> dict[str, object]:
        if code in ("SYN-MISSING-SEMICOLON", "SYN-UNEXPECTED-EOF"):
            r = self.rules[-1] if self.rules else "program"
            return {"context": "the expression" if r in EXPRESSION_RULES else RULE_PHRASES.get(r, "the " + r.replace("_", " "))}
        if code == "SYN-UNBALANCED-BRACKET":
            want = OPENER_OF.get(expected[0]) if expected and expected[0] in OPENER_OF else None
            if want is None:                                  # rule 3 via a stray closer
                return {"opener": OPENER_OF.get(tok.text, "?"), "open_line": "?"}
            for b in reversed(self.brackets):
                if b.text == want:
                    return {"opener": b.text, "open_line": b.line}
            return {"opener": want, "open_line": "?"}
        if code == "SYN-UNSUPPORTED-FEATURE":
            if tok.text == "*":
                return {"feature": "A pointer ('*' after a type)"}
            if tok.kind is K.UNSUPPORTED_OP:
                return {"feature": f"The operator '{tok.text}'"}
            return {"feature": f"'{tok.text}'"}
        return {}

    def report(self, code: str, tok: Token, expected: list[str], *,
               at: tuple[int, int] | None = None) -> str:
        """Create one syntax record through the sink; returns its id."""
        if at is not None or tok.kind is K.EOF:
            line, col = at if at is not None else (tok.line, tok.col)
            span_end = Position(line, col)                      # zero-width (8)
        else:
            line, col = tok.line, tok.col
            span_end = Position(tok.end_line, tok.end_col)
        rule_ref = (self.rules[-1] if self.rules else "program") if code in PRODUCTION_CODES else None
        rec = self.sink.report(code, line, col, found=tok.text, expected=expected, span_end=span_end,
                               caused_by=self.caused_by(tok), rule_ref=rule_ref,
                               **self.message_args(code, tok, expected))
        if code == "SYN-UNEXPECTED-EOF" and self.recovering is None:
            self.recovering = rec.id                              # 4.5: an EOF error opens the region
        return rec.id

    def fail(self, expected: list[str]) -> NoReturn:
        tok = self.cur
        code = self.select_code(tok, expected)
        raise ParseError(self.report(code, tok, expected), code)
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `53 passed`
- Commit `src/cea/parser.py tests/unit/test_parser_core.py`: `cea: add parser core and syntax-code selection (plan 006 step 2)`

### Step 3: Happy-path grammar (no recovery yet)

Append Listing 3a and then Listing 3b to the end of `src/cea/parser.py`, inside `class Parser` (both listings are already indented by 4 spaces; keep one blank line between methods). Then create `tests/unit/test_parser_grammar.py` with exactly Listing T3.

- Listing 3a is the **recovery section with stubs**. Each stub is a placeholder that Steps 4–9 replace with the real method. The stubs make the grammar run on valid input: `expect_semi` is a plain `expect(";")`, `expect_header_close` a plain `expect(")")`, `check_missing_brace`/`open_region`/`guard` do nothing, `declared_names` returns `[]`, `broken_decl` returns the statement unchanged, `is_lvalue` returns `True`, and the panic and error-node helpers raise `NotImplementedError` (they are only reached on bad input).
- Listing 3b is the **complete grammar**: one method per EBNF rule, named after the rule and decorated with `@rule("<name>")`. The non-obvious parts:
  - `top_decl` disambiguation (language-spec: "`top_decl` chooses `function_def` when the token after `IDENT` is `(`"): after `type_spec`, if the current token is `IDENT` and the next is `(`, call `function_def`, else `global_decl`.
  - `params`: `)` → `[]`; `void` followed by `)` → consume `void`, `[]`; otherwise **commit** to `param_list` (§4.1), so `int f(a)` fails inside `param`'s `type_spec` with SYN-EXPECTED-TYPE.
  - `function_def`: after the header `)`, a `{` starts the body; anything else goes to `expect_semi()` (site S1: a prototype).
  - Operator precedence, lowest to highest (each binary level is left-associative; assignment is right-associative):

    | Level (method) | Operators |
    |---|---|
    | `assignment` | `=` `+=` `-=` `*=` `/=` `%=` (right-assoc; lvalue check, Step 9) |
    | `logic_or` | `\|\|` |
    | `logic_and` | `&&` |
    | `equality` | `==` `!=` |
    | `comparison` | `<` `<=` `>` `>=` |
    | `term` | `+` `-` |
    | `factor` | `*` `/` `%` |
    | `unary` | prefix `!` `-` `+` `++` `--` |
    | `postfix` | calls `f(...)`, indexing `a[...]`, then at most one postfix `++`/`--` |
    | `primary` | literals, `IDENT`, `( expression )` |
  - Statement dispatch (`statement_body`): UNSUPPORTED_KEYWORD → error (rule 0); type keyword → `var_decl`; `if`/`while`/`for`/`return`/`break`/`continue` → `<kw>_stmt`; `{` → `block`; `;` → `empty_stmt`; anything else → `expr_stmt`.
  - The catch points (`statement`, `top_decl`, `guarded_expression`) and the `BlockRepair` handlers are already in their final form; they call the stubbed helpers.

**Listing 3a — append (recovery section, stubs)**

```python
    # =================================================== recovery (steps 4-9)
    def expect_semi(self) -> Token | None:
        return self.expect(";")

    def expect_header_close(self) -> None:
        self.expect(")")

    def check_missing_brace(self) -> None:
        return None

    def open_region(self, error_id: str) -> None:
        return None

    def panic_stmt(self) -> str | None:
        raise NotImplementedError("plan 006 step 5")

    def panic_for_header(self, base: int) -> str:
        raise NotImplementedError("plan 006 step 5")

    def first_on_line(self, i: int) -> bool:
        raise NotImplementedError("plan 006 step 5")

    def panic_top(self) -> str:
        raise NotImplementedError("plan 006 step 5")

    @staticmethod
    def kind_hint(tok: Token) -> str:
        raise NotImplementedError("plan 006 step 5")

    def idents(self, i: int, j: int) -> set[str]:
        raise NotImplementedError("plan 006 step 5")

    def error_stmt(self, e: ParseError, start: int, kind: str, stopped: str | None,
                   names: list[tuple[str, str]]) -> A.ErrorStmt:
        raise NotImplementedError("plan 006 step 5")

    def recover_top(self, e: ParseError, start: int, first: Token, stopped: str):
        raise NotImplementedError("plan 006 step 5")

    def declared_names(self, start: int, end: int, code: str) -> list[tuple[str, str]]:
        return []

    def broken_decl(self, stmt: A.VarDeclStmt, e: ParseError, start: int) -> A.VarDeclStmt:
        return stmt

    def guard(self, before: int) -> None:
        return None

    def is_lvalue(self, e: A.Expr) -> bool:
        return True

    def invalid_target(self, op: Token) -> NoReturn:
        raise NotImplementedError("plan 006 step 9")

```

**Listing 3b — append (grammar section)**

```python
    # ==================================================== grammar (step 3)
    @rule("program")
    def program(self) -> A.Program:
        decls: list = []
        while self.cur.kind is not K.EOF:
            before = self.pos
            decls.append(self.top_decl())
            self.guard(before)
        eof = self.toks[-1]                    # contract: 1:1 .. the EOF position
        return A.Program(decls, A.Span(1, 1, eof.line, eof.col))

    @rule("top_decl")
    def top_decl(self) -> A.FunctionDecl | A.VarDeclStmt | A.ErrorStmt:
        start, depth, first = self.pos, len(self.brackets), self.cur
        saved_ctx, saved_partial = self.top_ctx, self.partial_decl
        self.top_ctx, self.partial_decl = _TopCtx(), None
        try:
            type_tok = self.type_spec()
            if self.cur.kind is K.IDENT and self.is_(self.peek(1), "("):
                return self.function_def(type_tok, start)
            return self.global_decl(type_tok, start)
        except ParseError as e:                                            # catch point (c)
            del self.brackets[depth:]
            self.open_region(e.error_id)
            stopped = self.panic_top()
            return self.recover_top(e, start, first, stopped)
        finally:
            self.top_ctx, self.partial_decl = saved_ctx, saved_partial

    @rule("function_def")
    def function_def(self, type_tok: Token, start: int) -> A.FunctionDecl:
        name = self.consume()                               # IDENT (checked by top_decl)
        self.top_ctx.func_name, self.top_ctx.func_name_index = name, self.pos - 1
        self.match("(")
        params = self.params()
        self.expect(")")
        node = A.FunctionDecl(type_tok.text, name.text, Position(name.line, name.col), params, None,
                              self.span_from(start))
        self.top_ctx.func_node = node
        if self.at("{"):
            try:
                node.body = self.block()
            except BlockRepair as r:                        # 4.7: body closed by the repair
                node.body = r.node if isinstance(r.node, A.Block) else None
        else:
            self.expect_semi()                              # site S1
        node.span = self.span_from(start)
        return node

    @rule("params")
    def params(self) -> list[A.Param]:
        if self.at(")"):
            return []
        if self.at("void") and self.is_(self.peek(1), ")"):
            self.consume()
            return []
        return self.param_list()

    @rule("param_list")
    def param_list(self) -> list[A.Param]:
        out = [self.param()]
        while True:
            if self.at(","):
                self.consume()
                out.append(self.param())
            elif self.at(")"):
                return out
            else:
                self.fail([",", ")"])

    @rule("param")
    def param(self) -> A.Param:
        t = self.type_spec()
        name = self.expect_ident()
        return A.Param(t.text, name.text, Position(name.line, name.col),
                       A.Span(t.line, t.col, name.end_line, name.end_col))

    @rule("global_decl")
    def global_decl(self, type_tok: Token, start: int) -> A.VarDeclStmt:
        stmt = A.VarDeclStmt([], self.span_from(start))
        self.partial_decl = stmt
        self.declarator(type_tok.text, stmt, is_global=True)
        while self.at(","):
            self.consume()
            self.declarator(type_tok.text, stmt, is_global=True)
        self.expect_semi()                                  # site S2
        stmt.span = self.span_from(start)
        return stmt

    @rule("type_spec")
    def type_spec(self) -> Token:
        if is_type_kw(self.cur):
            return self.consume()
        self.fail([TYPE])

    @rule("declarator")
    def declarator(self, type_name: str, stmt: A.VarDeclStmt, is_global: bool) -> A.VarDecl:
        name = self.expect_ident()
        name_i = self.pos - 1
        node = A.VarDecl(type_name, name.text, Position(name.line, name.col), None, None, is_global,
                         self.span(name_i, name_i))
        stmt.decls.append(node)
        self.decl_log.append((name_i, name.text, type_name))
        self.name_index[id(node)] = name_i
        if self.at("["):
            self.array_suffix(node)
        if self.at("="):
            self.consume()
            node.init = self.guarded_expression(node, "init")       # CP-INIT
        node.span = self.span_from(name_i)
        return node

    @rule("array_suffix")
    def array_suffix(self, node: A.VarDecl) -> None:
        self.match("[")
        node.array_size = self.guarded_expression(node, "array_size")   # CP-SIZE
        self.expect("]")

    def guarded_expression(self, node: A.VarDecl, field: str) -> A.Expr:
        """CP-INIT / CP-SIZE (4.4 b): the failed expression becomes an ErrorExpr on the
        declaration; the ParseError is re-raised so the enclosing statement()/top_decl()
        runs the panic and returns the (broken) declaration."""
        start = self.pos
        try:
            return self.expression()
        except ParseError as e:
            setattr(node, field, A.ErrorExpr(self.span(start, self.pos - 1), e.error_id))
            raise

    @rule("block")
    def block(self) -> A.Block:
        start, depth = self.pos, len(self.brackets)
        orphan = self.recovering if self.stop_index == self.pos else None    # section 5 orphan_of
        self.match("{")
        node = A.Block([], self.span(start, start), orphan_of=orphan)
        self.block_orphans.append(orphan)
        try:
            while not (self.at("}") or self.cur.kind is K.EOF):
                before = self.pos
                node.stmts.append(self.statement())
                self.guard(before)
            if self.at("}"):
                self.match("}")
            else:
                self.report("SYN-UNEXPECTED-EOF", self.cur, ["}"])         # 4.4 EOF: no raise
            node.span = self.span_from(start)
            return node
        except BlockRepair as r:                                           # 4.7 propagation
            if r.node is not None:
                node.stmts.append(r.node)
            node.span = self.span_from(start)
            node.closed_by_repair = r.error_id
            r.node = node
            raise
        finally:
            self.block_orphans.pop()
            del self.brackets[depth:]

    @rule("statement")
    def statement(self) -> A.Stmt:
        start, depth, first = self.pos, len(self.brackets), self.cur
        saved_partial = self.partial_decl
        self.partial_decl = None
        try:
            self.check_missing_brace()                                     # 4.7 first
            return self.statement_body()
        except ParseError as e:                                            # catch point (a)
            kind = self.kind_hint(first)
            self.open_region(e.error_id)
            if e.in_for_header:
                stopped = self.panic_for_header(depth)
            else:
                stopped = self.panic_stmt()
            del self.brackets[depth:]
            if kind == "decl" and self.partial_decl is not None and self.partial_decl.decls:
                return self.broken_decl(self.partial_decl, e, start)
            return self.error_stmt(e, start, kind, stopped, self.declared_names(start, self.pos, e.code))
        finally:
            self.partial_decl = saved_partial

    def statement_body(self) -> A.Stmt:
        t = self.cur
        if t.kind is K.UNSUPPORTED_KEYWORD:
            self.fail([])                                                  # rule 0
        if is_type_kw(t):
            return self.var_decl()
        if t.kind is K.KEYWORD and t.text in STMT_KEYWORDS:
            return getattr(self, t.text + "_stmt")()
        if self.at("{"):
            return self.block()
        if self.at(";"):
            return self.empty_stmt()
        return self.expr_stmt()

    @rule("var_decl")
    def var_decl(self) -> A.VarDeclStmt:
        start = self.pos
        stmt = self.var_core(register=True)
        self.expect_semi()                                                 # site S3
        stmt.span = self.span_from(start)
        return stmt

    @rule("var_core")
    def var_core(self, register: bool) -> A.VarDeclStmt:
        start = self.pos
        type_tok = self.type_spec()
        stmt = A.VarDeclStmt([], self.span_from(start))
        if register:
            self.partial_decl = stmt
        self.declarator(type_tok.text, stmt, is_global=False)
        while self.at(","):
            self.consume()
            self.declarator(type_tok.text, stmt, is_global=False)
        stmt.span = self.span_from(start)
        return stmt

    @rule("if_stmt")
    def if_stmt(self) -> A.If:
        start = self.pos
        self.consume()                                                     # 'if'
        self.expect("(")
        cond = self.expression()
        self.expect_header_close()
        try:
            then = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.If(cond, r.node, None, self.span_from(start))
            raise
        els = None
        if self.at("else"):
            self.consume()
            try:
                els = self.statement()
            except BlockRepair as r:
                r.node = A.If(cond, then, r.node, self.span_from(start))
                raise
        return A.If(cond, then, els, self.span_from(start))

    @rule("while_stmt")
    def while_stmt(self) -> A.While:
        start = self.pos
        self.consume()                                                     # 'while'
        self.expect("(")
        cond = self.expression()
        self.expect_header_close()
        try:
            body = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.While(cond, r.node, self.span_from(start))
            raise
        return A.While(cond, body, self.span_from(start))

    @rule("for_stmt")
    def for_stmt(self) -> A.For:
        start = self.pos
        self.consume()                                                     # 'for'
        self.expect("(")
        try:
            init = None if self.at(";") else self.for_init()
            self.expect_semi()                                             # site S4
            cond = None if self.at(";") else self.expression()
            self.expect_semi()                                             # site S5
            step = None if self.at(")") else self.expression()
            self.expect_header_close()
        except ParseError as e:
            e.in_for_header = True
            raise
        try:
            body = self.statement()
        except BlockRepair as r:
            if r.node is not None:
                r.node = A.For(init, cond, step, r.node, self.span_from(start))
            raise
        return A.For(init, cond, step, body, self.span_from(start))

    @rule("for_init")
    def for_init(self) -> A.VarDeclStmt | A.Expr:
        if is_type_kw(self.cur):
            return self.var_core(register=False)
        return self.expression()

    @rule("return_stmt")
    def return_stmt(self) -> A.Return:
        start = self.pos
        self.consume()                                                     # 'return'
        value = None if self.at(";") else self.expression()
        self.expect_semi()                                                 # site S6
        return A.Return(value, self.span_from(start))

    @rule("break_stmt")
    def break_stmt(self) -> A.Break:
        start = self.pos
        self.consume()
        self.expect_semi()                                                 # site S7
        return A.Break(self.span_from(start))

    @rule("continue_stmt")
    def continue_stmt(self) -> A.Continue:
        start = self.pos
        self.consume()
        self.expect_semi()                                                 # site S8
        return A.Continue(self.span_from(start))

    @rule("expr_stmt")
    def expr_stmt(self) -> A.ExprStmt:
        start = self.pos
        e = self.expression()
        self.expect_semi()                                                 # site S9
        return A.ExprStmt(e, self.span_from(start))

    @rule("empty_stmt")
    def empty_stmt(self) -> A.EmptyStmt:
        start = self.pos
        self.match(";")                                                    # site S10
        return A.EmptyStmt(self.span_from(start))

    @rule("expression")
    def expression(self) -> A.Expr:
        return self.assignment()

    @rule("assignment")
    def assignment(self) -> A.Expr:
        left = self.logic_or()
        if self.at_any(ASSIGN_OPS):
            op = self.cur
            if not self.is_lvalue(left):
                self.invalid_target(op)
            self.consume()
            value = self.assignment()
            return A.Assign(op.text, left, value, Position(op.line, op.col), self.join(left.span, value.span))
        return left

    def binary(self, ops: tuple[str, ...], sub: Callable[[], A.Expr]) -> A.Expr:
        left = sub()
        while self.at_any(ops):
            op = self.consume()
            right = sub()
            left = A.Binary(op.text, left, right, Position(op.line, op.col), self.join(left.span, right.span))
        return left

    @rule("logic_or")
    def logic_or(self) -> A.Expr:
        return self.binary(("||",), self.logic_and)

    @rule("logic_and")
    def logic_and(self) -> A.Expr:
        return self.binary(("&&",), self.equality)

    @rule("equality")
    def equality(self) -> A.Expr:
        return self.binary(("==", "!="), self.comparison)

    @rule("comparison")
    def comparison(self) -> A.Expr:
        return self.binary(("<", "<=", ">", ">="), self.term)

    @rule("term")
    def term(self) -> A.Expr:
        return self.binary(("+", "-"), self.factor)

    @rule("factor")
    def factor(self) -> A.Expr:
        return self.binary(("*", "/", "%"), self.unary)

    @rule("unary")
    def unary(self) -> A.Expr:
        if self.at_any(("!", "-", "+", "++", "--")):
            op = self.consume()
            operand = self.unary()
            if op.text in ("++", "--") and not self.is_lvalue(operand):
                self.invalid_target(op)
            return A.Unary(op.text, operand, False,
                           A.Span(op.line, op.col, operand.span.end_line, operand.span.end_col))
        return self.postfix()

    @rule("postfix")
    def postfix(self) -> A.Expr:
        e = self.primary()
        while True:
            if self.at("("):
                self.match("(")
                args = [] if self.at(")") else self.arg_list()             # 4.1 lookahead commitment
                close = self.expect(")")
                e = A.Call(e, args, A.Span(e.span.start_line, e.span.start_col, close.end_line, close.end_col))
            elif self.at("["):
                self.match("[")
                idx = self.expression()
                close = self.expect("]")
                e = A.Index(e, idx, A.Span(e.span.start_line, e.span.start_col, close.end_line, close.end_col))
            else:
                break
        if self.at_any(("++", "--")):
            op = self.cur
            if not self.is_lvalue(e):
                self.invalid_target(op)
            self.consume()
            e = A.Unary(op.text, e, True, A.Span(e.span.start_line, e.span.start_col, op.end_line, op.end_col))
        return e

    @rule("arg_list")
    def arg_list(self) -> list[A.Expr]:
        out = [self.assignment()]
        while True:
            if self.at(","):
                self.consume()
                out.append(self.assignment())
            elif self.at(")"):
                return out
            else:
                self.fail([",", ")"])

    @rule("primary")
    def primary(self) -> A.Expr:
        t = self.cur
        lit = {K.INT_LIT: A.IntLit, K.FLOAT_LIT: A.FloatLit, K.CHAR_LIT: A.CharLit, K.STRING_LIT: A.StringLit}
        if t.kind in lit:
            self.consume()
            return lit[t.kind](t.value, A.Span(t.line, t.col, t.end_line, t.end_col))
        if t.kind is K.IDENT:
            self.consume()
            return A.Name(t.text, A.Span(t.line, t.col, t.end_line, t.end_col))
        if self.at("("):
            self.match("(")
            e = self.expression()
            self.expect(")")
            self.paren[id(e)] = e
            return e
        self.fail([EXPR])
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `82 passed` (includes zero syntax records and the structural check for all 12 `tests/corpus/valid/*.c`)
- `grep -c NotImplementedError src/cea/parser.py` → `9`
- Commit `src/cea/parser.py tests/unit/test_parser_grammar.py`: `cea: add happy-path grammar for the C subset (plan 006 step 3)`

### Step 4: Phrase repairs (§4.2 missing `;`, §4.3 missing `)` before `{`, §4.7 missing `}`)

In `src/cea/parser.py`, replace the three stubs `expect_semi`, `expect_header_close` and `check_missing_brace` (each stub is its `def` line plus one body line, exactly as in Listing 3a) with Listing 4. Create `tests/unit/test_parser_repairs.py` with exactly Listing T4.

**Listing 4 — replaces the three stubs**

```python
    def expect_semi(self) -> Token | None:
        """expect(';') with the 4.2 missing-';' repair."""
        tok = self.cur
        if self.is_(tok, ";"):
            return self.match(";")
        after = (self.prev.end_line, self.prev.end_col + 1)
        if tok.kind is not K.EOF and tok.line > self.prev.end_line:
            self.report("SYN-MISSING-SEMICOLON", tok, [";"], at=after)        # 4.2: repair, no panic
            return None
        code = self.select_code(tok, [";"])
        rid = self.report(code, tok, [";"], at=after if code == "SYN-MISSING-SEMICOLON" else None)
        raise ParseError(rid, code)

    def expect_header_close(self) -> None:
        """expect(')') closing an if/while/for header, with the 4.3 missing-')'-before-'{' repair."""
        if self.at(")"):
            self.match(")")
            return
        if self.at("{"):
            code = self.select_code(self.cur, [")"])                          # rule 3
            self.report(code, self.cur, [")"])
            if self.brackets and self.brackets[-1].text == "(":
                self.brackets.pop()                                           # as if ')' matched
            return
        self.fail([")"])

    def check_missing_brace(self) -> None:
        """4.7: `type IDENT (` at the start of a statement proves a missing '}'."""
        t0, t1, t2 = self.cur, self.peek(1), self.peek(2)
        if is_type_kw(t0) and t1.kind is K.IDENT and self.is_(t2, "("):
            code = self.select_code(t0, ["}"])                                # rule 3
            raise BlockRepair(self.report(code, t0, ["}"]))
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `86 passed`
- `grep -c NotImplementedError src/cea/parser.py` → `9`
- Commit `src/cea/parser.py tests/unit/test_parser_repairs.py`: `cea: add phrase-level repairs for ; ) and } (plan 006 step 4)`

### Step 5: Panic modes and sync sets (§4.4), ErrorStmt construction

Replace the stubs `panic_stmt`, `panic_for_header`, `first_on_line`, `panic_top`, `kind_hint` (its stub has an `@staticmethod` line above the `def`; replace all three lines), `idents`, `error_stmt` (its stub `def` spans two lines) and `recover_top` (its stub `def` spans one line) with Listing 5. Create `tests/unit/test_parser_panic.py` with exactly Listing T5.

**Listing 5 — replaces eight stubs**

```python
    def panic_stmt(self) -> str | None:
        """Statement-level panic (4.4). Returns stopped_before (None if a ';' was consumed)."""
        while True:
            tok = self.cur
            if tok.kind is K.EOF or (tok.kind in SYMBOLIC and tok.text in SYNC_STMT_STOP):
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, ";"):
                self.recovering = None                                        # 4.5 (i)
                return None

    def panic_for_header(self, base: int) -> str:
        """For-header panic (4.4). `base` = bracket depth before the header's '('."""
        d = sum(1 for b in self.brackets[base:] if b.text == "(")
        while True:
            tok = self.cur
            if tok.kind is K.EOF or (tok.kind in SYMBOLIC and tok.text in SYNC_STMT_STOP):
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, "("):
                d += 1
            elif self.is_(tok, ")"):
                d -= 1
                if d == 0:
                    self.stop_index = self.pos
                    return self.cur.text

    def first_on_line(self, i: int) -> bool:
        return i == 0 or self.toks[i - 1].line < self.toks[i].line

    def panic_top(self) -> str:
        """Top-level panic (4.4). Returns the text of the token it stopped before."""
        depth = 0
        while True:
            tok = self.cur
            if tok.kind is K.EOF:
                self.stop_index = self.pos
                return tok.text
            if is_type_kw(tok) and depth == 0 and self.first_on_line(self.pos):
                self.recovering = None                                        # 4.5 (ii)
                self.stop_index = self.pos
                return tok.text
            self.consume()
            if self.is_(tok, "{"):
                depth += 1
            elif self.is_(tok, "}"):
                depth = max(0, depth - 1)

    @staticmethod
    def kind_hint(tok: Token) -> str:
        if tok.kind is K.UNSUPPORTED_KEYWORD:
            return "unsupported"
        if tok.kind is K.KEYWORD:
            if tok.text in TYPE_KEYWORDS:
                return "decl"
            if tok.text in STMT_KEYWORDS:
                return tok.text
        return "expr"

    def idents(self, i: int, j: int) -> set[str]:
        return {t.text for t in self.toks[i:j] if t.kind is K.IDENT}

    def error_stmt(self, e: ParseError, start: int, kind: str, stopped: str | None,
                   names: list[tuple[str, str]]) -> A.ErrorStmt:
        if kind == "unsupported":
            self.unsupported_ids.add(e.error_id)
        return A.ErrorStmt(span=self.span_from(start), error_id=e.error_id, kind_hint=kind,
                           declared_names=names, idents_in_span=self.idents(start, self.pos),
                           stopped_before=stopped)

    def recover_top(self, e: ParseError, start: int, first: Token, stopped: str):
        ctx = self.top_ctx
        if ctx.func_node is not None:                       # error after the header: broken function
            ctx.func_node.error_id = e.error_id
            ctx.func_node.idents_in_span = self.idents(ctx.func_name_index, self.pos)
            ctx.func_node.span = self.span_from(start)
            return ctx.func_node
        if ctx.func_name is not None:                       # error inside the header (5)
            names = [(ctx.func_name.text, "function")]
            names += [n for n in self.declared_names(start, self.pos, e.code)
                      if n[1] == "<unsupported>" and n[0] != ctx.func_name.text]
            return self.error_stmt(e, start, "top", stopped, names)
        if self.partial_decl is not None and self.partial_decl.decls:
            return self.broken_decl(self.partial_decl, e, start)
        kind = "unsupported" if first.kind is K.UNSUPPORTED_KEYWORD else "top"
        return self.error_stmt(e, start, kind, stopped, self.declared_names(start, self.pos, e.code))
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `94 passed`
- `grep -c NotImplementedError src/cea/parser.py` → `1` (only `invalid_target`, replaced in Step 9)
- Commit `src/cea/parser.py tests/unit/test_parser_panic.py`: `cea: add statement, for-header and top-level panic (plan 006 step 5)`

### Step 6: The uncertain region and R2/R1/R9 (§4.5, §7)

`caused_by()` (Step 2), the region closing in `match()`/`panic_stmt()`/`panic_top()`, the EOF opening in `report()` and the `orphan_of`/`block_orphans` bookkeeping in `block()` are already in place. Until now the region was never opened by a panic. Replace the stub `open_region` with Listing 6 and create `tests/unit/test_parser_region.py` with exactly Listing T6.

**Listing 6 — replaces the `open_region` stub**

```python
    def open_region(self, error_id: str) -> None:
        if self.recovering is None:
            self.recovering = error_id
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `99 passed`
- Commit `src/cea/parser.py tests/unit/test_parser_region.py`: `cea: open the uncertain region on panic; R2/R1/R9 links (plan 006 step 6)`

### Step 7: Error nodes and broken declarations (§5, plan-004 rules)

Replace the stubs `declared_names` and `broken_decl` with Listing 7. `declared_names` combines the `type_spec IDENT` pairs logged by `declarator()` inside the span with, for a SYN-UNSUPPORTED-FEATURE error only, the plan-004 declarator pattern. Create `tests/unit/test_parser_error_nodes.py` with exactly Listing T7.

**Listing 7 — replaces two stubs**

```python
    def declared_names(self, start: int, end: int, code: str) -> list[tuple[str, str]]:
        """ErrorStmt.declared_names: consumed `type_spec IDENT` pairs, plus (plan 004) the
        declarator-like names of an unsupported-feature error, in source order, no duplicates."""
        found = [(i, n, t) for (i, n, t) in self.decl_log if start <= i < end]
        if code == "SYN-UNSUPPORTED-FEATURE":
            for i in range(max(start, 1), end):
                tok, before, after = self.toks[i], self.toks[i - 1], self.toks[i + 1]
                if (tok.kind is K.IDENT
                        and (is_type_kw(before) or self.is_(before, "*") or before.kind is K.IDENT)
                        and after.kind in SYMBOLIC and after.text in ("=", ";", ",", "[")):
                    found.append((i, tok.text, "<unsupported>"))
        out: list[tuple[str, str]] = []
        for _, name, typ in sorted(found):
            if name not in [n for n, _ in out]:
                out.append((name, typ))
        return out

    def broken_decl(self, stmt: A.VarDeclStmt, e: ParseError, start: int) -> A.VarDeclStmt:
        """Section 5: keep the declaration; the last declarator gets error_id and idents_in_span."""
        last = stmt.decls[-1]
        name_i = self.name_index[id(last)]
        last.error_id = e.error_id
        last.idents_in_span = self.idents(name_i, self.pos)
        last.span = self.span_from(name_i)
        stmt.span = self.span_from(start)
        return stmt
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `105 passed`
- Commit `src/cea/parser.py tests/unit/test_parser_error_nodes.py`: `cea: add broken declarations and declared_names (plan 006 step 7)`

### Step 8: The progress loop guard (§4.6 point 3)

Replace the stub `guard` with Listing 8. `STRICT_PROGRESS` (module flag, default `False`) makes the guard raise `ProgressError` instead of skipping a token; every parser test file sets it to `True` with an autouse fixture. Create `tests/unit/test_parser_progress.py` with exactly Listing T8. **Do not run `test_parser_progress.py` before replacing the stub**: with the stub, its deliberately stuck parser loops forever.

**Listing 8 — replaces the `guard` stub**

```python
    def guard(self, before: int) -> None:
        """Loop guard (4.6 point 3)."""
        if self.pos == before:
            if STRICT_PROGRESS:
                raise ProgressError(f"no progress at token {before}: {self.cur!r}")
            self.consume()
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `108 passed`
- Commit `src/cea/parser.py tests/unit/test_parser_progress.py`: `cea: add the parser progress guard (plan 006 step 8)`

### Step 9: The lvalue check (SYN-INVALID-ASSIGN-TARGET)

Replace the stubs `is_lvalue` and `invalid_target` with Listing 9. Create `tests/unit/test_parser_lvalue.py` with exactly Listing T9.

**Listing 9 — replaces two stubs**

```python
    def is_lvalue(self, e: A.Expr) -> bool:
        if id(e) in self.paren:
            return False
        if isinstance(e, A.Name):
            return True
        return isinstance(e, A.Index) and isinstance(e.base, A.Name) and id(e.base) not in self.paren

    def invalid_target(self, op: Token) -> NoReturn:
        """SYN-INVALID-ASSIGN-TARGET at the assignment/increment operator."""
        raise ParseError(self.report("SYN-INVALID-ASSIGN-TARGET", op, []), "SYN-INVALID-ASSIGN-TARGET")
```

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `121 passed`
- `grep -c NotImplementedError src/cea/parser.py` → `0`
- Commit `src/cea/parser.py tests/unit/test_parser_lvalue.py`: `cea: reject non-lvalue assignment targets (plan 006 step 9)`

### Step 10: Reference traces T1–T9 and the catalog example triggers

Create `tests/unit/test_parser_traces.py` with exactly Listing T10. It asserts, for every trace of `docs/error-recovery.md` §9, the exact lexical and syntax records (the lexer runs first in the same sink, so in T5 and T6 the lexical record is E-0001 and the syntax record E-0002), the AST facts each trace narrative states, and one row per SYN code from the catalog's "Example trigger" column. The expected syntax records (semantic records are plan 007's):

| Trace | Id | Code | Line:Col | Found | Expected | caused_by |
|---|---|---|---|---|---|---|
| T1 | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | `[";"]` | — |
| T1b | E-0001 | SYN-MISSING-SEMICOLON | 3:14 | a | `[";"]` | — |
| T2 | E-0001 | SYN-UNBALANCED-BRACKET | 6:1 | int | `["}"]` | — |
| T3 | E-0001 | SYN-EXPECTED-TOKEN | 3:8 | x | `["("]` | — |
| T5 | E-0001 | LEX-INVALID-CHAR (lexer) | 2:15 | @ | `[]` | — |
| T5 | E-0002 | SYN-MISSING-SEMICOLON | 2:14 | 2 | `[";"]` | E-0001 (R1) |
| T6 | E-0001 | LEX-INVALID-ESCAPE (lexer) | 4:18 | \q | `[]` | — |
| T6 | E-0002 | SYN-MISSING-SEMICOLON | 5:22 | result | `[";"]` | — |
| T7 | E-0001 | SYN-UNBALANCED-BRACKET | 3:19 | { | `[")"]` | — |
| T8 | E-0001 | SYN-UNSUPPORTED-FEATURE | 3:5 | switch | `[]` | — |
| T8 | E-0002 | SYN-UNSUPPORTED-FEATURE | 4:9 | case | `[]` | E-0001 (R2) |
| T8 | E-0003 | SYN-UNSUPPORTED-FEATURE | 7:9 | default | `[]` | E-0001 (R9) |
| T9 | E-0001 | SYN-UNSUPPORTED-FEATURE | 2:9 | * | `["identifier"]` | — |

(T4 has no lexical or syntax record.)

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `146 passed`
- Commit `tests/unit/test_parser_traces.py`: `test: pin parser records for traces T1-T9 and catalog examples (plan 006 step 10)`

### Step 11: Corpus checks and the single-token-deletion robustness test

Create `tests/unit/test_parser_corpus.py` with exactly Listing T11. It:
- checks that every `tests/corpus/dev` program whose sidecar has a `SYN-` root reports a syntax record with that `(code, line)` (20 programs: `008`–`015`, `040`–`042`, `044`, `045`, `048`–`052`, `060`, `062`);
- pins the exact syntax records `(code, line:col, found, caused_by)` of all 54 dev programs (`DEV_SYNTAX`; programs not listed must have none). These agree with every sidecar's `notes` trace;
- deletes each single token of each `tests/corpus/valid` program in turn (1 146 parses), parses with `STRICT_PROGRESS = True`, and requires: no exception (the progress guard never fires), only `SYN-` records, and every `caused_by` pointing to an earlier record.

It never reads `tests/corpus/heldout/`.

**Verify**:
- `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `233 passed`
- `grep -c heldout tests/unit/test_parser_*.py` → each file `0` except `test_parser_corpus.py`, which mentions it once, in its docstring.
- Commit `tests/unit/test_parser_corpus.py`: `test: check the parser against the dev and valid corpus (plan 006 step 11)`

### Step 12: Whole-suite check, plan-007 interface probe, status row

1. `.venv/Scripts/python -m pytest -q` → `591 passed, 1 skipped` (B + 233). The skip is still `tests/test_corpus_compile.py`.
2. `test -e src/cea/pipeline.py && echo PRESENT || echo absent` → `absent`.
3. `grep -n 'print(' src/cea/ast.py src/cea/parser.py` → no output.
4. Plan 007's Step 1 probes (it will STOP if these differ), each must print exactly the value shown:
   - `.venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='void g(void) {\n}\n'; k=ErrorSink(s); lr=lex(s,k); p=parse(lr,k); print(p.span.end_line, p.span.end_col, lr.tokens[-1].line, lr.tokens[-1].col, len(k.records))"` → `2 2 2 2 0`
   - `.venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n'; k=ErrorSink(s); p=parse(lex(s,k),k); e=p.decls[0].body.stmts[0]; print(type(e).__name__, e.kind_hint, e.declared_names, e.error_id)"` → `ErrorStmt decl [('p', '<unsupported>')] E-0001`
   - `.venv/Scripts/python -c "import sys; sys.path.insert(0,'src'); from cea.diagnostics import ErrorSink; from cea.lexer import lex; from cea.parser import parse; s='int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n'; k=ErrorSink(s); p=parse(lex(s,k),k); b=p.decls[0].body.stmts; print(b[1].kind_hint, b[1].stopped_before, b[2].orphan_of, [type(x).__name__ for x in b[2].stmts], [r.caused_by for r in k.records])"` → `unsupported { E-0001 ['ErrorStmt', 'Break', 'ErrorStmt'] [None, 'E-0001', 'E-0001']`
5. Update this plan's row in `plans/README.md` to `DONE (branch advisor/006-m1-parser, not merged)` unless a reviewer maintains the index. Commit `plans/README.md`: `plans: mark plan 006 done (plan 006 step 12)`.
6. `git status --short` → empty. `git diff --name-only main..HEAD | sort` → exactly the 13 in-scope files plus `plans/README.md`.

## Test plan

All new tests are in `tests/unit/`, written in the style of `tests/test_corpus_schema.py` (module docstring, small helpers, plain `assert`, `pytest.mark.parametrize` tables). Every parser test file has an autouse fixture that sets `cea.parser.STRICT_PROGRESS = True`, so a loop-guard trip is a test failure everywhere.

| File (step) | Tests | Covers |
|---|---|---|
| `test_parser_ast.py` (1) | 30 | contract field names/order for all 27 node classes; frozen `Span`; recovery-field defaults; no stdlib shadowing |
| `test_parser_core.py` (2) | 23 | bracket stack and region closing in `match()`; `expect()` failure creates exactly one record; selection rules 0–5 (15 rows incl. rule 0 beating rule 2, rule 1 beating rule 2, stray closer); R2 > R1 > R9 precedence; innermost `rule_ref` and unwinding; zero-width EOF record opens the region; `PRODUCTION_CODES` equals the catalog's `<production>` rows and every rule name is a language-spec §2 rule |
| `test_parser_grammar.py` (3) | 29 | 11 precedence/associativity rows; `top_decl` disambiguation, `()`/`(void)`, prototypes; every statement kind and the dangling `else`; inclusive spans; empty file; `Program.span` ends at the EOF position (`int main(void) { return 0; }` → `Span(1, 1, 1, 29)`); 200 nested parentheses; all 12 valid corpus programs: zero syntax records, no error nodes, function names equal the source's function headers |
| `test_parser_repairs.py` (4) | 4 | §4.2 at all nine `;` sites S1–S9 (no region opened); §4.3 for `if`/`while`/`for`; §4.7 closing three nested blocks with one record and keeping the nested `while`/`if`; one SYN-UNEXPECTED-EOF per open block, the second linked by R2 |
| `test_parser_panic.py` (5) | 8 | same-line missing `;` panics; statement panic stops before a sync keyword; for-header panic consumes the header `)` and counts nested parentheses; top-level panic skips an indented `int` at depth 1; stray `}` at top level; openers of a failed statement are forgotten |
| `test_parser_region.py` (6) | 5 | R2 until the next `;`; R1 from `lex_gap`; R9 only in the innermost orphan block of an `unsupported` ErrorStmt; top-level panic closes the region; `orphan_of` after statement and for-header panic |
| `test_parser_error_nodes.py` (7) | 6 | broken local/global declarations with `ErrorExpr`; broken `FunctionDecl`; `kind_hint='unsupported'` and plan-004 declarator names (`N`, `p`, `q`, `s`, `v`; not `t` after `,`); names only for unsupported errors; `for (int i …, j …` declares both; the array-initialiser cascade |
| `test_parser_progress.py` (8) | 3 | guard raises in strict mode, skips otherwise; token soup never raises |
| `test_parser_lvalue.py` (9) | 13 | 8 invalid targets (`5 =`, `x + 1 =`, `(x) =`, `a[1][2] =`, `f(x) +=`, `5++`, `--(x)`, `3++`) and 5 valid ones |
| `test_parser_traces.py` (10) | 25 | T1, T1b, T2, T3, T5, T6, T7, T8, T9 exact records + AST facts; 10 catalog example triggers incl. array initialiser and array parameter |
| `test_parser_corpus.py` (11) | 87 | 20 SYN-root dev programs; 54 exact dev syntax tables; 12 valid programs × every single-token deletion (1 146 parses) |
| **Total** | **233** | |

Mutation checks run on the scratch prototype (each made at least one test fail; you may repeat any of them, then revert with `git checkout -- src/cea/parser.py`): disabling the §4.2 repair, the §4.3 repair, the §4.7 repair, R9, R2-before-R1 order, the EOF region opening, `orphan_of`, rule 3's stray-closer clause, the for-header panic, the region closing at a top-level sync keyword, the bracket truncation in `statement()`, broken declarations, the plan-004 names, the lvalue check, and `[",", ")"]` in `param_list` (→ `[")"]`).

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` → `591 passed, 1 skipped` (B = 358 at `66fb191`, plus 233)
- [ ] `.venv/Scripts/python -m pytest -q tests/unit/test_parser_*.py` → `233 passed`
- [ ] `grep -c NotImplementedError src/cea/parser.py` → `0`
- [ ] `src/cea/pipeline.py` does not exist; `grep -n 'print(' src/cea/ast.py src/cea/parser.py` prints nothing
- [ ] The three plan-007 probes in Step 12 print exactly the expected lines
- [ ] `git diff --name-only main..HEAD` lists only the 13 in-scope files and `plans/README.md`
- [ ] One commit per Step 1–11 (+ the README commit), each message ending with the `Co-Authored-By` line
- [ ] The final report ends with a **Viva notes** list

## STOP conditions

Stop and report (do not improvise) if:

- The drift check fails, or the Step 0 baseline is not `358 passed, 1 skipped`.
- A reference trace (T1–T9 table in Step 10) cannot be reproduced with the code exactly as listed, or reproducing it would contradict a rule quoted in "Current state". Never change a reference answer in a test.
- The progress guard fires (`ProgressError`) on any corpus input, or any test raises `RecursionError`.
- The contract's AST fields are insufficient for something this plan needs (for example plan 007 asks for a field that `ast.py` lacks). Do not add or rename fields: report.
- `ErrorSink.report()` rejects a call from the parser (`ValueError` for a `rule_ref`, `KeyError` for a message placeholder, `TypeError` for `expected`): plan 005 and this plan disagree on the contract.
- A step's verification count differs after one careful comparison of your file with the listing.
- Any change seems to need a file outside "Scope" (including `docs/`, `tests/corpus/`, or a plan-005 module).

## Maintenance notes

- **Plan 007 reads**: `ErrorStmt.declared_names` (R5, including `(name, "function")` and `"<unsupported>"` names), `idents_in_span` (R6), `Block.orphan_of` together with the `kind_hint` of the `ErrorStmt` whose `error_id` it names (R7: `while`/`for`/`unsupported`), `Block.closed_by_repair` and nested `ErrorStmt`s (R8), broken `VarDecl`/`FunctionDecl` (`error_id`, R4/R5), `ErrorExpr.error_id` (R3) and `Program.span` end (SEM-MISSING-MAIN position). Changing any of these breaks plan 007's trace tests.
- **Reviewer focus**: `statement()`'s catch (for-header vs statement panic, broken declaration vs `ErrorStmt`), `block()`'s `orphan` test and `BlockRepair` handler, `expect_semi()` (§4.2 vs panic vs EOF), and `select_code()` ordering.
- **Known limitations (accepted, all mechanical)**:
  - The plan-004 declarator pattern misses a declarator after `,` (`char *s = 0, t;` declares only `s`) and a name after an unsupported type modifier (`long count = 0;`: `long` is not a type keyword, so `count` is not recovered and its later uses stay unlinked). Fixing either needs a spec amendment of error-recovery §5.
  - For-header panic leaves the region open until the body's first `;`/`}` (spec §4.5 "Known limitation"), so an independent error there is over-linked by R2.
  - R9 may over-link an independent error inside an unsupported construct's body (spec §7, accepted).
  - The catalog's SYN-UNBALANCED-BRACKET template assumes an opener; for a stray closer (rule 3, second clause) the message reads "… to close '(' from line ? …". A catalog follow-up could add a template for this case.
  - The `expected` classes `expression`/`type`/`identifier` are not token texts (D1). If the AI layer (F3) needs to tell them apart, prefer a typed field in a later contract revision over string matching.
  - `parse()` temporarily raises the interpreter recursion limit (D13). It is restored in `finally`; the parser is not meant to run concurrently in threads.
- **Deferred**: special messages for array initialisers/array parameters (the README follow-up suggested SYN-UNSUPPORTED-FEATURE; the advisor chose the literal catalog behaviour, D2); `language-spec.md` §6 still says "SYN-UNSUPPORTED-FEATURE or SYN-EXPECTED-TOKEN" and should be tightened in a docs plan to "SYN-EXPECTED-EXPRESSION (`= {`) or SYN-EXPECTED-TOKEN (`[` in a parameter)".

## Appendix A: Test listings

**Listing T1 — `tests/unit/test_parser_ast.py`**

```python
"""AST contract checks for src/cea/ast.py (plan 006 step 1).

The field names and order are fixed by plans/m1-architecture.md section 4;
plan 007 consumes them, so any drift must fail here.
"""
import dataclasses

import pytest

from cea import ast as A
from cea.records import Position

CONTRACT = {
    "Span": ["start_line", "start_col", "end_line", "end_col"],
    "Program": ["decls", "span"],
    "Param": ["type_name", "name", "name_pos", "span"],
    "FunctionDecl": ["ret_type", "name", "name_pos", "params", "body", "span", "error_id", "idents_in_span"],
    "VarDecl": ["type_name", "name", "name_pos", "array_size", "init", "is_global", "span",
                "error_id", "idents_in_span"],
    "VarDeclStmt": ["decls", "span"],
    "Block": ["stmts", "span", "orphan_of", "closed_by_repair"],
    "If": ["cond", "then", "els", "span"],
    "While": ["cond", "body", "span"],
    "For": ["init", "cond", "step", "body", "span"],
    "Return": ["value", "span"],
    "Break": ["span"],
    "Continue": ["span"],
    "ExprStmt": ["expr", "span"],
    "EmptyStmt": ["span"],
    "ErrorStmt": ["span", "error_id", "kind_hint", "declared_names", "idents_in_span", "stopped_before"],
    "IntLit": ["value", "span"],
    "FloatLit": ["value", "span"],
    "CharLit": ["value", "span"],
    "StringLit": ["value", "span"],
    "Name": ["name", "span"],
    "Unary": ["op", "operand", "postfix", "span"],
    "Binary": ["op", "left", "right", "op_pos", "span"],
    "Assign": ["op", "target", "value", "op_pos", "span"],
    "Call": ["callee", "args", "span"],
    "Index": ["base", "index", "span"],
    "ErrorExpr": ["span", "error_id"],
}
SP = A.Span(1, 1, 1, 1)


@pytest.mark.parametrize("name,fields", sorted(CONTRACT.items()))
def test_node_fields_match_contract(name, fields):
    cls = getattr(A, name)
    assert dataclasses.is_dataclass(cls), f"{name} must be a dataclass"
    assert [f.name for f in dataclasses.fields(cls)] == fields


def test_span_is_frozen_and_hashable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SP.start_line = 2  # type: ignore[misc]
    assert hash(SP) == hash(A.Span(1, 1, 1, 1))


def test_recovery_fields_default_to_empty():
    f1 = A.FunctionDecl("int", "f", Position(1, 5), [], None, SP)
    f2 = A.FunctionDecl("int", "g", Position(1, 5), [], None, SP)
    assert f1.error_id is None and f1.idents_in_span == set()
    assert f1.idents_in_span is not f2.idents_in_span        # default_factory, not a shared set
    v = A.VarDecl("int", "x", Position(1, 5), None, None, False, SP)
    assert v.error_id is None and v.idents_in_span == set()
    b = A.Block([], SP)
    assert b.orphan_of is None and b.closed_by_repair is None


def test_module_does_not_shadow_stdlib_ast():
    import ast as stdlib_ast
    assert hasattr(stdlib_ast, "parse") and stdlib_ast is not A
    assert A.__name__ == "cea.ast"
```

**Listing T2 — `tests/unit/test_parser_core.py`**

```python
"""Parser core: cursor, expect(), catalog code selection (rules 0-5), bracket
stack, caused_by precedence and rule_ref (plan 006 step 2)."""
import dataclasses

import pytest

from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


def make(src):
    sink = ErrorSink(src)
    return P.Parser(lex(src, sink).tokens, sink), sink


def at_text(p, text):
    """Move the cursor to the first token with this text."""
    p.pos = next(i for i, t in enumerate(p.toks) if t.text == text)
    return p


def test_cursor_and_match_track_brackets():
    p, _ = make("( [ { } ] )")
    for t in "([{":
        p.match(t)
    assert [b.text for b in p.brackets] == ["(", "[", "{"]
    for t in "}])":
        p.match(t)
    assert p.brackets == [] and p.cur.kind is P.K.EOF
    assert p.consume().kind is P.K.EOF and p.pos == len(p.toks) - 1   # EOF is never passed


def test_match_semicolon_and_brace_close_region():
    p, _ = make("; }")
    p.recovering = "E-0009"
    p.match(";")
    assert p.recovering is None
    p.recovering = "E-0009"
    p.match("}")
    assert p.recovering is None


def test_expect_failure_raises_after_one_record():
    p, sink = make("x")
    p.rules.append("if_stmt")
    with pytest.raises(P.ParseError) as ei:
        p.expect("(")
    (rec,) = sink.records
    assert ei.value.error_id == rec.id == "E-0001" and ei.value.code == rec.code == "SYN-EXPECTED-TOKEN"
    assert (rec.line, rec.column, rec.found, rec.expected, rec.rule_ref) == (1, 1, "x", ["("], "if_stmt")
    assert rec.message == "Expected '(' but found 'x'"


@pytest.mark.parametrize("src,found,expected,code", [
    ("switch", "switch", [";"], "SYN-UNSUPPORTED-FEATURE"),       # rule 0 beats rule 2
    ("a & b", "&", [";"], "SYN-UNSUPPORTED-FEATURE"),             # rule 0: UNSUPPORTED_OP
    ("int * p", "*", [P.IDENT], "SYN-UNSUPPORTED-FEATURE"),        # rule 0: '*' directly after type_spec
    ("x * p", "*", [P.IDENT], "SYN-EXPECTED-TOKEN"),               # '*' after a non-type is ordinary
    ("x", "EOF", [";"], "SYN-UNEXPECTED-EOF"),                     # rule 1 beats rule 2
    ("x y", "y", [";"], "SYN-MISSING-SEMICOLON"),                  # rule 2
    ("x y", "y", [")"], "SYN-UNBALANCED-BRACKET"),                 # rule 3: only closing brackets
    ("x y", "y", ["]"], "SYN-UNBALANCED-BRACKET"),
    ("x y", "y", ["}"], "SYN-UNBALANCED-BRACKET"),
    ("x )", ")", [P.EXPR], "SYN-UNBALANCED-BRACKET"),              # rule 3: stray closer, no opener
    ("x y", "y", [P.EXPR], "SYN-EXPECTED-EXPRESSION"),             # rule 4
    ("x y", "y", [P.TYPE], "SYN-EXPECTED-TYPE"),                   # rule 4
    ("x y", "y", ["("], "SYN-EXPECTED-TOKEN"),                     # rule 5
    ("x y", "y", [",", ")"], "SYN-EXPECTED-TOKEN"),                # ',' is not a closing bracket
    ("x y", "y", [P.IDENT], "SYN-EXPECTED-TOKEN"),
])
def test_select_code_rules_0_to_5(src, found, expected, code):
    p, _ = make(src)
    at_text(p, found) if found != "EOF" else setattr(p, "pos", len(p.toks) - 1)
    assert p.select_code(p.cur, expected) == code


def test_stray_closer_uses_only_matched_openers():
    p, _ = make("( )")
    p.pos = 1
    assert p.select_code(p.cur, [P.EXPR]) == "SYN-UNBALANCED-BRACKET"   # '(' was never matched
    p.pos = 0
    p.match("(")
    assert p.select_code(p.cur, [P.EXPR]) == "SYN-EXPECTED-EXPRESSION"  # now it has an opener


def test_caused_by_precedence_r2_then_r1_then_r9():
    p, sink = make("int main(void) { int x = 5 @ 2; }")      # '2' carries lex_gap E-0001
    tok = at_text(p, "2").cur
    assert tok.lex_gap == "E-0001"
    p.block_orphans.append("E-0005")
    p.unsupported_ids.add("E-0005")
    p.recovering = "E-0003"
    assert p.caused_by(tok) == "E-0003"                       # R2
    p.recovering = None
    assert p.caused_by(tok) == "E-0001"                       # R1
    assert p.caused_by(dataclasses.replace(tok, lex_gap=None)) == "E-0005"   # R9
    p.unsupported_ids.clear()
    assert p.caused_by(dataclasses.replace(tok, lex_gap=None)) is None


def test_rule_ref_is_innermost_rule_and_unwinds():
    class Probe(P.Parser):
        @P.rule("statement")
        def outer(self):
            return self.inner()

        @P.rule("primary")
        def inner(self):
            self.fail([P.EXPR])

    sink = ErrorSink("x")
    probe = Probe(lex("x", sink).tokens, sink)
    with pytest.raises(P.ParseError):
        probe.outer()
    assert sink.records[0].rule_ref == "primary" and probe.rules == []


def test_eof_record_is_zero_width_and_opens_region():
    p, sink = make("x")
    p.pos = 1
    p.rules.append("block")
    rid = p.report("SYN-UNEXPECTED-EOF", p.cur, ["}"])
    rec = sink.records[0]
    assert (rec.line, rec.column, rec.span_end.line, rec.span_end.column) == (1, 2, 1, 2)
    assert rec.found == "EOF" and rec.message == "File ended inside the block; expected '}'"
    assert p.recovering == rid


def test_production_codes_and_rule_names_match_the_docs():
    from cea.catalog import load_catalog, load_grammar_rules
    cat = load_catalog()
    assert P.PRODUCTION_CODES == {c for c, e in cat.items() if e.rule_ref == "<production>"}
    used = {name for name in dir(P.Parser)
            if getattr(getattr(P.Parser, name), "__wrapped__", None) is not None}
    assert used <= load_grammar_rules(), used - load_grammar_rules()
    assert set(P.RULE_PHRASES) <= load_grammar_rules()
```

**Listing T3 — `tests/unit/test_parser_grammar.py`**

```python
"""Happy-path grammar (plan 006 step 3): docs/language-spec.md section 2 on
valid input. Every tests/corpus/valid program must parse with zero syntax
records and the expected top-level structure."""
import re
from pathlib import Path

import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex

ROOT = Path(__file__).resolve().parents[2]
VALID = sorted((ROOT / "tests" / "corpus" / "valid").glob("*.c"))
FUNC_HEADER = re.compile(r"^(?:int|float|double|char|void)\s+([A-Za-z_]\w*)\s*\(", re.M)


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, [r for r in sink.records if r.phase == "syntax"]


def sx(e):
    """Compact s-expression of an expression, for precedence checks."""
    if isinstance(e, (A.IntLit, A.FloatLit)):
        return str(e.value)
    if isinstance(e, A.CharLit):
        return repr(e.value)
    if isinstance(e, A.StringLit):
        return '"' + e.value + '"'
    if isinstance(e, A.Name):
        return e.name
    if isinstance(e, A.Unary):
        return f"({e.op}{'post' if e.postfix else ''} {sx(e.operand)})"
    if isinstance(e, (A.Binary, A.Assign)):
        left = e.left if isinstance(e, A.Binary) else e.target
        right = e.right if isinstance(e, A.Binary) else e.value
        return f"({e.op} {sx(left)} {sx(right)})"
    if isinstance(e, A.Call):
        return f"(call {sx(e.callee)}{''.join(' ' + sx(a) for a in e.args)})"
    if isinstance(e, A.Index):
        return f"(idx {sx(e.base)} {sx(e.index)})"
    return type(e).__name__


def expr_of(src_expr):
    prog, syn = parse_src(f"int main(void) {{ {src_expr}; }}")
    assert syn == []
    return prog.decls[0].body.stmts[0].expr


def walk(node):
    yield node
    if isinstance(node, list):
        for x in node:
            yield from walk(x)
    elif hasattr(node, "__dataclass_fields__"):
        for name in node.__dataclass_fields__:
            v = getattr(node, name)
            if isinstance(v, list) or hasattr(v, "__dataclass_fields__"):
                yield from walk(v)


@pytest.mark.parametrize("src,want", [
    ("a = b = c", "(= a (= b c))"),                       # assignment is right-associative
    ("a += b || c && d", "(+= a (|| b (&& c d)))"),
    ("a == b < c + d * e", "(== a (< b (+ c (* d e))))"),
    ("a - b - c", "(- (- a b) c)"),                       # binary levels are left-associative
    ("a != b == c", "(== (!= a b) c)"),
    ("-a * !b % c", "(% (* (- a) (! b)) c)"),
    ("++i + j--", "(+ (++ i) (--post j))"),
    ("f(1, x[2]) / (a + b)", "(/ (call f 1 (idx x 2)) (+ a b))"),
    ("printf(\"%d\\n\", n)", "(call printf \"%d\n\" n)"),
    ("x = 'c' + 2.5", "(= x (+ 'c' 2.5))"),
    ("a[i] = a[i - 1] % 2", "(= (idx a i) (% (idx a (- i 1)) 2))"),
])
def test_operator_precedence(src, want):
    assert sx(expr_of(src)) == want


def test_top_decl_disambiguation_and_params():
    prog, syn = parse_src("int g = 1, h[3];\nint f(void);\nint k();\n"
                          "double m(int a, char b) { return a; }\nvoid z(void) { }\n")
    assert syn == []
    g, f, k, m, z = prog.decls
    assert isinstance(g, A.VarDeclStmt) and [(d.name, d.is_global) for d in g.decls] == [("g", True), ("h", True)]
    assert isinstance(g.decls[1].array_size, A.IntLit) and isinstance(g.decls[0].init, A.IntLit)
    assert (f.name, f.params, f.body) == ("f", [], None)          # (void) -> [] ; prototype -> body None
    assert (k.name, k.params, k.body) == ("k", [], None)
    assert [(p.type_name, p.name) for p in m.params] == [("int", "a"), ("char", "b")]
    assert m.ret_type == "double" and isinstance(m.body, A.Block)
    assert (m.name_pos.line, m.name_pos.column) == (4, 8)
    assert z.body.stmts == []


def test_statements_and_dangling_else():
    src = ("int main(void) {\n"
           "    int i, a[4];\n"
           "    for (int j = 0; j < 4; j++) a[j] = j;\n"
           "    for (;;) { break; }\n"
           "    while (i) { continue; }\n"
           "    if (i) if (a[0]) i = 1; else i = 2;\n"
           "    { ; }\n"
           "    return;\n"
           "}\n")
    prog, syn = parse_src(src)
    assert syn == []
    s = prog.decls[0].body.stmts
    assert [type(x).__name__ for x in s] == ["VarDeclStmt", "For", "For", "While", "If", "Block", "Return"]
    assert isinstance(s[1].init, A.VarDeclStmt) and s[1].init.decls[0].name == "j"
    assert (s[2].init, s[2].cond, s[2].step) == (None, None, None)
    assert isinstance(s[2].body.stmts[0], A.Break) and isinstance(s[3].body.stmts[0], A.Continue)
    assert s[4].els is None and isinstance(s[4].then, A.If) and s[4].then.els is not None   # else binds nearest
    assert isinstance(s[5].stmts[0], A.EmptyStmt) and s[6].value is None


def test_spans_are_inclusive_and_one_based():
    prog, _ = parse_src("int main(void) {\n    return 42;\n}\n")
    fn = prog.decls[0]
    assert fn.span == A.Span(1, 1, 3, 1)
    assert fn.body.stmts[0].span == A.Span(2, 5, 2, 14)          # 'return' .. ';'
    assert fn.body.stmts[0].value.span == A.Span(2, 12, 2, 13)


def test_empty_file_gives_empty_program():
    prog, syn = parse_src("")
    assert prog.decls == [] and syn == [] and prog.span == A.Span(1, 1, 1, 1)


@pytest.mark.parametrize("path", VALID, ids=[p.name for p in VALID])
def test_valid_corpus_parses_cleanly(path):
    src = path.read_text(encoding="utf-8")
    prog, syn = parse_src(src)
    assert syn == [], [(r.code, r.line, r.column) for r in syn]
    nodes = list(walk(prog))
    assert not any(isinstance(n, (A.ErrorStmt, A.ErrorExpr)) for n in nodes)
    assert not any(isinstance(n, A.Block) and (n.orphan_of or n.closed_by_repair) for n in nodes)
    funcs = [d for d in prog.decls if isinstance(d, A.FunctionDecl)]
    assert [f.name for f in funcs] == FUNC_HEADER.findall(src)
    assert all(f.error_id is None for f in funcs) and any(f.name == "main" for f in funcs)
    assert all(isinstance(d, (A.FunctionDecl, A.VarDeclStmt)) for d in prog.decls)


def test_deep_nesting_does_not_hit_recursion_limit():
    import sys
    before = sys.getrecursionlimit()
    depth = 200
    e = expr_of("x = " + "(" * depth + "1" + ")" * depth)
    assert sx(e) == "(= x 1)" and sys.getrecursionlimit() == before


def test_program_span_ends_at_eof_position():
    prog, _ = parse_src("int main(void) { return 0; }")
    assert prog.span == A.Span(1, 1, 1, 29)                   # EOF is right after the final '}'
    prog, _ = parse_src("\n\nint main(void) {\n    return 0;\n}\n")
    assert prog.span == A.Span(1, 1, 5, 2)
```

**Listing T4 — `tests/unit/test_parser_repairs.py`**

```python
"""Phrase-level repairs (plan 006 step 4): missing ';' (error-recovery 4.2),
missing ')' before '{' (4.3) and missing '}' (4.7), plus EOF inside blocks (4.4)."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- 4.2 / 4.3 / 4.7
def test_missing_semicolon_repair_at_every_site():
    src = ("int p(void)\n"                    # S1 prototype
           "int g = 1\n"                      # S2 global
           "int main(void) {\n"
           "    int a = 1\n"                  # S3
           "    for (a = 0\n"                 # S4
           "         a < 3\n"                 # S5
           "         a++) { }\n"
           "    a = 2\n"                      # S9
           "    while (a) { break\n"          # S7
           "    continue\n"                   # S8
           "    }\n"
           "    return a\n"                   # S6
           "}\n")
    prog, recs = parse_src(src)
    assert [(c, lc) for _, c, lc, _, _ in rows(recs)] == [("SYN-MISSING-SEMICOLON", lc) for lc in (
        "1:12", "2:10", "4:14", "5:15", "6:15", "8:10", "9:22", "10:13", "12:13")]
    assert all(cb is None for *_, cb in rows(recs))                    # repairs never open a region
    assert not any(isinstance(s, A.ErrorStmt) for s in body(prog, 2))
    assert isinstance(body(prog, 2)[1], A.For)


def test_missing_paren_before_brace_keeps_if_while_for():
    prog, recs = parse_src(main("int i = 0;", "if (i < 3 { i = 1; }", "while (i {", "break;", "}",
                                "for (i = 0; i < 2; i++ { continue; }", "return i;"))
    assert [(c, lc, f) for _, c, lc, f, _ in rows(recs)] == [
        ("SYN-UNBALANCED-BRACKET", "3:15", "{"), ("SYN-UNBALANCED-BRACKET", "4:14", "{"),
        ("SYN-UNBALANCED-BRACKET", "7:28", "{")]
    assert recs[0].message == "Expected ')' to close '(' from line 3 but found '{'"
    assert [type(s).__name__ for s in body(prog)] == ["VarDeclStmt", "If", "While", "For", "Return"]


def test_missing_brace_repair_closes_every_open_block():
    src = ("int f(int a) {\n"
           "    while (a) {\n"
           "        if (a > 2) {\n"
           "            a = a - 1;\n"
           "int main(void) {\n"
           "    return f(3);\n"
           "}\n")
    prog, recs = parse_src(src)
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "5:1", "int", None)]
    assert recs[0].expected == ["}"] and recs[0].rule_ref == "statement"
    assert recs[0].message == "Expected '}' to close '{' from line 3 but found 'int'"
    f, m = prog.decls
    assert f.name == "f" and m.name == "main" and f.error_id is None
    assert f.body.closed_by_repair == "E-0001" and f.body.span == A.Span(1, 14, 4, 22)
    loop = f.body.stmts[0]
    assert isinstance(loop, A.While) and loop.body.closed_by_repair == "E-0001"
    inner_if = loop.body.stmts[0]
    assert isinstance(inner_if, A.If) and inner_if.then.closed_by_repair == "E-0001"
    assert isinstance(inner_if.then.stmts[0], A.ExprStmt)


def test_missing_brace_in_last_function_reports_eof_per_block():
    prog, recs = parse_src("int main(void) {\n    while (1) {\n        return 0;\n")
    assert rows(recs) == [("E-0001", "SYN-UNEXPECTED-EOF", "3:18", "EOF", None),
                          ("E-0002", "SYN-UNEXPECTED-EOF", "3:18", "EOF", "E-0001")]
    assert recs[0].expected == ["}"] and recs[0].span_end.column == 18
    assert isinstance(prog.decls[0].body.stmts[0], A.While)
```

**Listing T5 — `tests/unit/test_parser_panic.py`**

```python
"""Panic modes and sync sets (plan 006 step 5): statement-level, for-header
and top-level panic (error-recovery 4.4) and the ErrorStmt they produce."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


def test_missing_semicolon_same_line_panics():
    prog, recs = parse_src(main("int a = 1;", "a = 2 a = 3;", "return a;"))
    assert rows(recs) == [("E-0001", "SYN-MISSING-SEMICOLON", "3:10", "a", None)]
    st = body(prog)[1]
    assert isinstance(st, A.ErrorStmt) and st.kind_hint == "expr" and st.stopped_before is None
    assert st.span == A.Span(3, 5, 3, 16) and st.idents_in_span == {"a"}


def test_missing_paren_before_non_brace_is_ordinary_error():
    prog, recs = parse_src(main("int i = 0;", "if (i < 3 i = 1;", "return i;"))
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "3:15", "i", None)]
    assert isinstance(body(prog)[1], A.ErrorStmt)


# ---------------------------------------------------------------- 4.4 panic modes
def test_statement_panic_stops_before_sync_token():
    prog, recs = parse_src(main("int x = 1;", "x = x + ) if (x) { x = 2; }", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "3:13", ")", None)]
    err, nxt = body(prog)[1], body(prog)[2]
    assert isinstance(err, A.ErrorStmt) and err.stopped_before == "if" and err.kind_hint == "expr"
    assert isinstance(nxt, A.If)


def test_for_header_panic_consumes_header_close_paren():
    prog, recs = parse_src(main("int n = 3;", "for (int i = 0 i < n; i++) {", "n = n + i;", "}", "return n;"))
    assert rows(recs) == [("E-0001", "SYN-MISSING-SEMICOLON", "3:19", "i", None)]
    err, block = body(prog)[1], body(prog)[2]
    assert isinstance(err, A.ErrorStmt) and err.kind_hint == "for" and err.stopped_before == "{"
    assert err.idents_in_span == {"i", "n"} and err.span == A.Span(3, 5, 3, 30)
    assert isinstance(block, A.Block)


def test_for_header_panic_counts_nested_parens():
    prog, recs = parse_src(main("int n = 3;", "for (n = (1 + ; (n)); n++) n = 1;", "return n;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-EXPRESSION", "3:19", ";", None)]
    assert body(prog)[1].stopped_before == "n"                # stopped after the header's own ')'
    assert isinstance(body(prog)[2], A.ExprStmt)


def test_top_level_panic_resyncs_at_type_keyword_first_on_line():
    src = ("int f(a, int b) {\n"
           "    int c = b;\n"                    # indented 'int' at depth 1: not a sync point
           "    return c;\n"
           "}\n"
           "int main(void) { return 0; }\n")
    prog, recs = parse_src(src)
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TYPE", "1:7", "a", None)]
    err, m = prog.decls
    assert isinstance(err, A.ErrorStmt) and err.kind_hint == "top"
    assert err.declared_names == [("f", "function")] and err.stopped_before == "int"
    assert err.span == A.Span(1, 1, 4, 1) and m.name == "main"


def test_stray_closing_brace_at_top_level():
    prog, recs = parse_src("int main(void) { return 0; }\n}\nint g;\n")
    assert rows(recs) == [("E-0001", "SYN-UNBALANCED-BRACKET", "2:1", "}", None)]
    assert recs[0].rule_ref == "type_spec"
    assert [type(d).__name__ for d in prog.decls] == ["FunctionDecl", "ErrorStmt", "VarDeclStmt"]


def test_brackets_opened_in_a_failed_statement_are_forgotten():
    prog, recs = parse_src(main("int x = 1;", "x = (1 + ;", ");", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-EXPRESSION", "3:14", ";", None),
                          ("E-0002", "SYN-UNBALANCED-BRACKET", "4:5", ")", None)]   # stray: its '(' was dropped
```

**Listing T6 — `tests/unit/test_parser_region.py`**

```python
"""Uncertain region and caused_by for syntax records (plan 006 step 6):
error-recovery 4.5 and rules R2, then R1, then R9 (section 7, plan 004)."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- 4.5 region, R1/R2/R9
def test_region_links_follow_on_errors_until_semicolon():
    prog, recs = parse_src(main("int x = 1;", "if x > 0) { x = ; }", "x = ;", "return x;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TOKEN", "3:8", "x", None),
                          ("E-0002", "SYN-EXPECTED-EXPRESSION", "3:21", ";", "E-0001"),
                          ("E-0003", "SYN-EXPECTED-EXPRESSION", "4:9", ";", None)]


def test_r1_lex_gap_links_syntax_record():
    prog, recs = parse_src(main("int x = 1;", "x = @;", "return x;"))
    assert [(r.code, f"{r.line}:{r.column}", r.caused_by) for r in recs] == [
        ("LEX-INVALID-CHAR", "3:9", None), ("SYN-EXPECTED-EXPRESSION", "3:10", "E-0001")]


def test_r9_links_errors_in_unsupported_orphan_body_only():
    src = main("int n = 1;", "do {", "n = 2;", "case 3: n = 4;", "{ default: n = 5; }", "} while (n);",
               "case 6: n = 7;", "return n;")
    prog, recs = parse_src(src)
    assert rows(recs) == [
        ("E-0001", "SYN-UNSUPPORTED-FEATURE", "3:5", "do", None),
        ("E-0002", "SYN-UNSUPPORTED-FEATURE", "5:5", "case", "E-0001"),    # R9 (region closed by 'n = 2;')
        ("E-0003", "SYN-UNSUPPORTED-FEATURE", "6:7", "default", None),     # inner block is not the orphan
        ("E-0004", "SYN-UNSUPPORTED-FEATURE", "8:5", "case", None)]        # outside the orphan body
    assert isinstance(body(prog)[3], A.While)        # '} while (n);' is a real while with an empty body
    assert body(prog)[1].kind_hint == "unsupported" and body(prog)[2].orphan_of == "E-0001"


def test_top_level_panic_closes_region_at_sync_keyword():
    prog, recs = parse_src("int f(a) { return 0; }\nint main(void) { int x = ; return 0; }\n")
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-TYPE", "1:7", "a", None),
                          ("E-0002", "SYN-EXPECTED-EXPRESSION", "2:26", ";", None)]


def test_orphan_block_after_panic():
    prog, recs = parse_src(main("int n = 3;", "for (int i = 0 i < n; i++) {", "n = n + i;", "}",
                                "while n) { n = 1; }", "{ n = 2; }", "return n;"))
    assert [r.id for r in recs] == ["E-0001", "E-0002"]
    s = body(prog)
    assert s[2].orphan_of == "E-0001" and s[4].orphan_of == "E-0002"
    assert s[5].orphan_of is None                       # not preceded by a panic stop
```

**Listing T7 — `tests/unit/test_parser_error_nodes.py`**

```python
"""Error nodes and broken declarations (plan 006 step 7): error-recovery
section 5 including the plan-004 'unsupported' kind_hint and declarator names."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- 5 error nodes
def test_broken_declarations_keep_their_names():
    prog, recs = parse_src(main("int a = 1, b = ;", "double c[2;", "int d = 1, 5;", "return a;"))
    s = body(prog)
    assert [(r.code, f"{r.line}:{r.column}") for r in recs] == [
        ("SYN-EXPECTED-EXPRESSION", "2:20"), ("SYN-UNBALANCED-BRACKET", "3:15"), ("SYN-EXPECTED-TOKEN", "4:16")]
    a, b = s[0].decls
    assert a.error_id is None and isinstance(a.init, A.IntLit)
    assert b.error_id == "E-0001" and b.init == A.ErrorExpr(A.Span(2, 20, 2, 20), "E-0001")
    assert b.idents_in_span == {"b"}
    (c,) = s[1].decls
    assert c.error_id == "E-0002" and isinstance(c.array_size, A.IntLit) and c.init is None
    (d,) = s[2].decls
    assert d.error_id == "E-0003" and d.name == "d"


def test_broken_global_and_broken_function():
    prog, recs = parse_src("int g = ;\nint f(void) x\nint main(void) { return 0; }\n")
    assert [(r.code, f"{r.line}:{r.column}") for r in recs] == [
        ("SYN-EXPECTED-EXPRESSION", "1:9"), ("SYN-MISSING-SEMICOLON", "2:12")]
    g, f, m = prog.decls
    assert g.decls[0].is_global and g.decls[0].error_id == "E-0001" and isinstance(g.decls[0].init, A.ErrorExpr)
    assert isinstance(f, A.FunctionDecl) and f.error_id == "E-0002" and f.body is None
    assert f.idents_in_span == {"f", "x"} and m.name == "main"


def test_unsupported_kind_hint_and_declarator_names():
    src = ("const int N = 5;\n"
           "int k;\n"
           "struct point p, *q;\n"
           "int main(void) {\n"
           "    unsigned int u = 1;\n"
           "    char *s = 0, t;\n"
           "    int *v[3];\n"
           "    return N;\n"
           "}\n")
    prog, recs = parse_src(src)
    assert [(r.code, f"{r.line}:{r.column}", r.found) for r in recs] == [
        ("SYN-UNSUPPORTED-FEATURE", "1:1", "const"), ("SYN-UNSUPPORTED-FEATURE", "3:1", "struct"),
        ("SYN-UNSUPPORTED-FEATURE", "5:5", "unsigned"), ("SYN-UNSUPPORTED-FEATURE", "6:10", "*"),
        ("SYN-UNSUPPORTED-FEATURE", "7:9", "*")]
    e1, e2 = prog.decls[0], prog.decls[2]
    assert (e1.kind_hint, e1.declared_names) == ("unsupported", [("N", "<unsupported>")])
    assert (e2.kind_hint, e2.declared_names) == ("unsupported", [("p", "<unsupported>"), ("q", "<unsupported>")])
    s = body(prog, 3)
    assert s[0].kind_hint == "unsupported" and s[0].declared_names == [] and s[0].stopped_before == "int"
    assert isinstance(s[1], A.VarDeclStmt) and s[1].decls[0].name == "u"     # 'int u = 1;' parses normally
    assert (s[2].kind_hint, s[2].declared_names) == ("decl", [("s", "<unsupported>")])   # t follows "," so the plan-004 pattern skips it
    assert s[3].declared_names == [("v", "<unsupported>")]


def test_declarator_names_only_for_unsupported_errors():
    prog, _ = parse_src(main("int 5 x = 1;", "return 0;"))
    err = body(prog)[0]
    assert err.kind_hint == "decl" and err.declared_names == []         # SYN-EXPECTED-TOKEN, not unsupported


def test_for_header_error_stmt_declares_loop_variable():
    prog, _ = parse_src(main("int n = 3;", "for (int i = 0, j = 1 i < n; i++) { n = i; }", "return n;"))
    assert body(prog)[1].declared_names == [("i", "int"), ("j", "int")]


def test_array_initialiser_list_cascade_is_linked():
    prog, recs = parse_src(main("int a[3] = {1, 2};", "return 0;"))
    assert rows(recs) == [("E-0001", "SYN-EXPECTED-EXPRESSION", "2:16", "{", None),
                          ("E-0002", "SYN-MISSING-SEMICOLON", "2:18", ",", "E-0001")]
    decl, orphan = body(prog)[0], body(prog)[1]
    assert decl.decls[0].error_id == "E-0001" and isinstance(decl.decls[0].init, A.ErrorExpr)
    assert isinstance(orphan, A.Block) and orphan.orphan_of == "E-0001"
```

**Listing T8 — `tests/unit/test_parser_progress.py`**

```python
"""Progress guarantee (plan 006 step 8): the loop guard of error-recovery 4.6."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- 4.6 progress guard
def test_progress_guard_raises_in_strict_mode():
    class Stuck(P.Parser):
        def top_decl(self):                       # consumes nothing: a deliberately broken production
            return A.ErrorStmt(A.Span(1, 1, 1, 1), "E-0000", "top", [], set(), None)

    sink = ErrorSink("int x;")
    stuck = Stuck(lex("int x;", sink).tokens, sink)
    with pytest.raises(P.ProgressError):
        stuck.program()


def test_progress_guard_skips_a_token_when_not_strict(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", False)

    class Stuck(P.Parser):
        def top_decl(self):
            return A.ErrorStmt(A.Span(1, 1, 1, 1), "E-0000", "top", [], set(), None)

    sink = ErrorSink("int x;")
    stuck = Stuck(lex("int x;", sink).tokens, sink)
    assert len(stuck.program().decls) == 3                 # one forced skip per token: int, x, ;


def test_parse_never_raises_on_token_soup():
    src = "} ) ] ; , else = + int ( [ { if while for return 1 x \"s\" 'c' 2.5 & switch"
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    assert isinstance(prog, A.Program) and all(r.phase == "syntax" for r in sink.records)
```

**Listing T9 — `tests/unit/test_parser_lvalue.py`**

```python
"""SYN-INVALID-ASSIGN-TARGET (plan 006 step 9): the lvalue rule of language-spec 2."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def parse_src(src):
    sink = ErrorSink(src)
    prog = P.parse(lex(src, sink), sink)
    return prog, sink.records


def rows(records):
    return [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
            for r in records if r.phase == "syntax"]


def body(prog, i=0):
    return prog.decls[i].body.stmts


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


# ---------------------------------------------------------------- lvalues
@pytest.mark.parametrize("stmt,col,found", [
    ("5 = x;", 7, "="), ("x + 1 = 2;", 11, "="), ("(x) = 1;", 9, "="), ("a[1][2] = 3;", 13, "="),
    ("f(x) += 1;", 10, "+="), ("5++;", 6, "++"), ("--(x);", 5, "--"), ("x = 3++;", 10, "++"),
])
def test_invalid_assign_target(stmt, col, found):
    prog, recs = parse_src(main("int x = 1;", stmt, "return x;"))
    assert rows(recs) == [("E-0001", "SYN-INVALID-ASSIGN-TARGET", f"3:{col}", found, None)]
    assert recs[0].rule_ref == "assignment" and recs[0].expected == []
    assert isinstance(body(prog)[1], A.ErrorStmt)


@pytest.mark.parametrize("stmt", ["x = 1;", "a[x] = 2;", "x++;", "--a[0];", "x += a[1] = 3;"])
def test_valid_assign_targets(stmt):
    _, recs = parse_src(main("int x = 1;", "int a[2];", stmt, "return x;"))
    assert rows(recs) == []
```

**Listing T10 — `tests/unit/test_parser_traces.py`**

```python
"""Syntax-record subsets of the reference traces T1-T9 (docs/error-recovery.md
section 9). Lexical records come first in the same sink, so they take the
first ids (T5, T6). Semantic records are asserted later by plan 007."""
import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import lex

TRACES = {
    "T1": "int main(void) {\n    int a = 1;\n    int b = 2\n    a = a + b;\n    return a;\n}\n",
    "T1b": "int main(void) {\n    int a = 1;\n    int b = 2 a = a + b;\n    return a;\n}\n",
    "T2": ("int f(int a) {\n    if (a > 0) {\n        a = a - 1;\n    return a;\n}\n"
           "int main(void) {\n    return f(3);\n}\n"),
    "T3": "int main(void) {\n    int x = 1;\n    if x > 0) {\n        x = 2;\n    }\n    return 0;\n}\n",
    "T5": "int main(void) {\n    int x = 5 @ 2;\n    return x;\n}\n",
    "T6": ("#include <stdio.h>\nint main(void) {\n    int count = 0;\n    printf(\"total\\q\\n\", count);\n"
           "    count = count + 1\n    result = count;\n    return 0;\n}\n"),
    "T7": ("int main(void) {\n    int i = 0;\n    while (i < 10 {\n        i = i + 1;\n        if (i == 5) {\n"
           "            break;\n        }\n    }\n    return i;\n}\n"),
    "T8": ("int main(void) {\n    int n = 2;\n    switch (n) {\n        case 1:\n            n = 5;\n"
           "            break;\n        default:\n            n = 0;\n    }\n    return n;\n}\n"),
    "T9": "int main(void) {\n    int *p;\n    p = 0;\n    return p;\n}\n",
}

# (id, code, line:col, found, expected, caused_by) for every lexical + syntax record
EXPECTED = {
    "T1": [("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", [";"], None)],
    "T1b": [("E-0001", "SYN-MISSING-SEMICOLON", "3:14", "a", [";"], None)],
    "T2": [("E-0001", "SYN-UNBALANCED-BRACKET", "6:1", "int", ["}"], None)],
    "T3": [("E-0001", "SYN-EXPECTED-TOKEN", "3:8", "x", ["("], None)],
    "T5": [("E-0001", "LEX-INVALID-CHAR", "2:15", "@", [], None),
           ("E-0002", "SYN-MISSING-SEMICOLON", "2:14", "2", [";"], "E-0001")],
    "T6": [("E-0001", "LEX-INVALID-ESCAPE", "4:18", "\\q", [], None),
           ("E-0002", "SYN-MISSING-SEMICOLON", "5:22", "result", [";"], None)],
    "T7": [("E-0001", "SYN-UNBALANCED-BRACKET", "3:19", "{", [")"], None)],
    "T8": [("E-0001", "SYN-UNSUPPORTED-FEATURE", "3:5", "switch", [], None),
           ("E-0002", "SYN-UNSUPPORTED-FEATURE", "4:9", "case", [], "E-0001"),
           ("E-0003", "SYN-UNSUPPORTED-FEATURE", "7:9", "default", [], "E-0001")],
    "T9": [("E-0001", "SYN-UNSUPPORTED-FEATURE", "2:9", "*", [P.IDENT], None)],
}


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def main(*lines):
    return "int main(void) {\n" + "".join(f"    {s}\n" for s in lines) + "}\n"


def run(name):
    src = TRACES[name]
    sink = ErrorSink(src)
    return P.parse(lex(src, sink), sink), sink.records


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_trace_records(name):
    _, recs = run(name)
    got = [(r.id, r.code, f"{r.line}:{r.column}", r.found, r.expected, r.caused_by) for r in recs]
    assert got == EXPECTED[name]


def test_t1b_broken_declaration():
    prog, _ = run("T1b")
    b = prog.decls[0].body.stmts[1].decls[0]
    assert (b.name, b.type_name, b.error_id, b.idents_in_span) == ("b", "int", "E-0001", {"a", "b"})


def test_t2_body_closed_by_repair():
    prog, _ = run("T2")
    f, m = prog.decls
    assert f.body.closed_by_repair == "E-0001" and m.name == "main" and m.body.closed_by_repair is None


def test_t3_error_stmt_and_orphan_block():
    prog, _ = run("T3")
    err, orphan = prog.decls[0].body.stmts[1:3]
    assert err == A.ErrorStmt(A.Span(3, 5, 3, 13), "E-0001", "if", [], {"x"}, "{")
    assert isinstance(orphan, A.Block) and orphan.orphan_of == "E-0001"


def test_t7_while_kept_with_condition_and_body():
    prog, _ = run("T7")
    loop = prog.decls[0].body.stmts[1]
    assert isinstance(loop, A.While) and loop.cond.op == "<"
    assert isinstance(loop.body.stmts[1].then.stmts[0], A.Break)


def test_t8_unsupported_orphan_body():
    prog, _ = run("T8")
    err, orphan = prog.decls[0].body.stmts[1:3]
    assert (err.kind_hint, err.stopped_before, err.declared_names) == ("unsupported", "{", [])
    assert orphan.orphan_of == "E-0001"
    assert [type(s).__name__ for s in orphan.stmts] == ["ErrorStmt", "Break", "ErrorStmt"]


def test_t9_declarator_name_recovered():
    prog, _ = run("T9")
    err = prog.decls[0].body.stmts[0]
    assert (err.kind_hint, err.declared_names) == ("decl", [("p", "<unsupported>")])


# The catalog's 'Example trigger' column, one row per SYN code, plus the two language-spec 6 cases.
# ---------------------------------------------------------------- catalog example triggers
@pytest.mark.parametrize("src,want", [
    (main("int x = 5", "return x;"), ("SYN-MISSING-SEMICOLON", "2:14", "return")),
    (main("int x = 2;", "if (x > 1 { }", "return 0;"), ("SYN-UNBALANCED-BRACKET", "3:15", "{")),
    (main("int x = 2;", "while x > 1) { }", "return 0;"), ("SYN-EXPECTED-TOKEN", "3:11", "x")),
    (main("int x = ;", "return 0;"), ("SYN-EXPECTED-EXPRESSION", "2:13", ";")),
    ("int f(a) { }\n", ("SYN-EXPECTED-TYPE", "1:7", "a")),
    ("int main() { return 0;", ("SYN-UNEXPECTED-EOF", "1:23", "EOF")),
    (main("int x = 1;", "5 = x;", "return 0;"), ("SYN-INVALID-ASSIGN-TARGET", "3:7", "=")),
    (main("int *p;", "return 0;"), ("SYN-UNSUPPORTED-FEATURE", "2:9", "*")),
    # language-spec 6: no special case; ordinary selection rules
    (main("int a[3] = {1, 2};", "return 0;"), ("SYN-EXPECTED-EXPRESSION", "2:16", "{")),
    ("int f(int a[]) { return 0; }\n", ("SYN-EXPECTED-TOKEN", "1:12", "[")),
])
def test_catalog_example_triggers(src, want):
    sink = ErrorSink(src)
    P.parse(lex(src, sink), sink)
    first = [r for r in sink.records if r.phase == "syntax"][0]
    assert (first.code, f"{first.line}:{first.column}", first.found) == want
```

**Listing T11 — `tests/unit/test_parser_corpus.py`**

```python
"""Parser against the corpus (plan 006): every dev program with a SYN root
reports it, the dev syntax records are exactly as traced, and single-token
deletions of every valid program never crash or trip the progress guard.
tests/corpus/heldout/ is deliberately never read here (corpus README section 5)."""
import json
from pathlib import Path

import pytest

from cea import ast as A
from cea import parser as P
from cea.diagnostics import ErrorSink
from cea.lexer import LexResult, lex

ROOT = Path(__file__).resolve().parents[2]
DEV = sorted((ROOT / "tests" / "corpus" / "dev").glob("*.c"))
VALID = sorted((ROOT / "tests" / "corpus" / "valid").glob("*.c"))


def sidecar(path):
    return json.loads(path.with_name(path.stem + ".expected.json").read_text(encoding="utf-8"))


SYN_DEV = [p for p in DEV if any(r["code"].startswith("SYN-") for r in sidecar(p)["roots"])]

# Exact syntax records (code, line:col, found, caused_by) observed for every dev
# program with at least one syntax record; matches each sidecar's "notes" trace.
DEV_SYNTAX = {
    "002": [("SYN-EXPECTED-EXPRESSION", "12:5", "return", "E-0001")],
    "003": [("SYN-EXPECTED-EXPRESSION", "5:22", ";", "E-0001")],
    "005": [("SYN-EXPECTED-EXPRESSION", "4:20", ";", "E-0001")],
    "008": [("SYN-MISSING-SEMICOLON", "8:22", "count", None)],
    "009": [("SYN-UNBALANCED-BRACKET", "6:20", "{", None)],
    "010": [("SYN-EXPECTED-TOKEN", "6:11", "count", None)],
    "011": [("SYN-EXPECTED-EXPRESSION", "12:21", ";", None)],
    "012": [("SYN-EXPECTED-TYPE", "3:9", "a", None)],
    "013": [("SYN-UNEXPECTED-EOF", "12:14", "EOF", None)],
    "014": [("SYN-INVALID-ASSIGN-TARGET", "12:7", "=", None)],
    "015": [("SYN-UNSUPPORTED-FEATURE", "4:5", "const", None)],
    "040": [("SYN-MISSING-SEMICOLON", "5:18", "int", None)],
    "041": [("SYN-UNBALANCED-BRACKET", "10:1", "int", None)],
    "042": [("SYN-UNEXPECTED-EOF", "12:2", "EOF", None)],
    "044": [("SYN-EXPECTED-EXPRESSION", "6:22", ";", None)],
    "045": [("SYN-EXPECTED-TOKEN", "7:11", "count", None)],
    "046": [("SYN-EXPECTED-EXPRESSION", "9:5", "if", "E-0001")],
    "048": [("SYN-MISSING-SEMICOLON", "3:15", "int", None)],
    "049": [("SYN-UNSUPPORTED-FEATURE", "6:9", "*", None)],
    "050": [("SYN-UNBALANCED-BRACKET", "7:28", "{", None)],
    "051": [("SYN-MISSING-SEMICOLON", "6:19", "i", None)],
    "052": [("SYN-UNSUPPORTED-FEATURE", "6:5", "switch", None),
            ("SYN-UNSUPPORTED-FEATURE", "7:9", "case", "E-0001"),
            ("SYN-UNSUPPORTED-FEATURE", "10:9", "case", "E-0001"),
            ("SYN-UNSUPPORTED-FEATURE", "13:9", "default", "E-0001")],
    "060": [("SYN-MISSING-SEMICOLON", "8:27", "return", None)],
    "062": [("SYN-EXPECTED-EXPRESSION", "4:20", ";", None)],
}


@pytest.fixture(autouse=True)
def strict_progress(monkeypatch):
    monkeypatch.setattr(P, "STRICT_PROGRESS", True)


def records_for(path):
    src = path.read_text(encoding="utf-8")
    sink = ErrorSink(src)
    P.parse(lex(src, sink), sink)
    return sink.records


def test_syn_dev_selection_is_not_empty():
    assert len(SYN_DEV) >= 20, [p.name for p in SYN_DEV]


@pytest.mark.parametrize("path", SYN_DEV, ids=[p.name for p in SYN_DEV])
def test_dev_syn_roots_are_reported(path):
    got = {(r.code, r.line) for r in records_for(path) if r.phase == "syntax"}
    want = [(r["code"], r["line"]) for r in sidecar(path)["roots"] if r["code"].startswith("SYN-")]
    assert all(w in got for w in want), f"want {want}, got {sorted(got)}"


@pytest.mark.parametrize("path", DEV, ids=[p.name for p in DEV])
def test_dev_syntax_records_exact(path):
    got = [(r.code, f"{r.line}:{r.column}", r.found, r.caused_by)
           for r in records_for(path) if r.phase == "syntax"]
    assert got == DEV_SYNTAX.get(path.name[:3], [])


def _deletion_cases():
    cases = []
    for path in VALID:
        src = path.read_text(encoding="utf-8")
        n = len(lex(src, ErrorSink(src)).tokens) - 1          # every token except EOF
        cases.append(pytest.param(path, n, id=path.name))
    return cases


@pytest.mark.parametrize("path,n_tokens", _deletion_cases())
def test_single_token_deletion_never_crashes(path, n_tokens):
    src = path.read_text(encoding="utf-8")
    base = lex(src, ErrorSink(src))
    for i in range(n_tokens):
        sink = ErrorSink(src)
        toks = base.tokens[:i] + base.tokens[i + 1:]
        prog = P.parse(LexResult(toks, base.stdio_include), sink)      # must not raise (incl. ProgressError)
        assert isinstance(prog, A.Program)
        ids = [r.id for r in sink.records]
        for r in sink.records:
            assert r.phase == "syntax" and r.code.startswith("SYN-")
            assert r.caused_by is None or r.caused_by in ids[:ids.index(r.id)], (i, r)
```

## Appendix B: How this plan was verified

The advisor ran every listing in a scratch copy outside the repo (`%TMP%\plan006real`): the real plan-005 modules from `main` (`src/cea/{catalog,diagnostics,lexer,records,tokens}.py`), `docs/`, `tests/corpus/dev` and `tests/corpus/valid` (never `heldout`), plus `ast.py`, `parser.py` and the 11 test files exactly as listed. Results:

- `pytest -q tests/unit` → `495 passed` (262 plan-005 unit tests + 233 parser tests).
- The step-by-step build was replayed with the Listing 3a stubs, replacing them step by step: cumulative parser tests 30 → 53 → 82 → 86 → 94 → 99 → 105 → 108 → 121 → 146 → 233, matching the Verify lines.
- Traces: T1, T1b, T2, T3, T5, T6, T7, T8 and T9 all **match** the reference record tables of `docs/error-recovery.md` §9 (id, code, line:col, found, caused_by).
- All 54 dev programs: the lexical and syntax records (code, line, linked or not) agree with every sidecar's `notes` trace (0 mismatches). All 12 valid programs: 0 records.
- Robustness: 1 146 single-token-deletion parses, 0 exceptions, 0 guard trips, at most 2 records per parse (code counts: MISSING-SEMICOLON 365, EXPECTED-EXPRESSION 298, EXPECTED-TOKEN 173, UNBALANCED-BRACKET 114, EXPECTED-TYPE 72, UNEXPECTED-EOF 30, INVALID-ASSIGN-TARGET 16).
- The three plan-007 Step 1 probes print exactly the expected lines.
- Full repo suite at `66fb191` before this plan: `358 passed, 1 skipped`.
