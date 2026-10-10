# Plan 001: Define the course C subset, its error catalog, and record the language decision

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: this folder is NOT a git repository. Instead run
> `sha256sum "cd project prd.docx"` from the project root. Expected prefix:
> `8377df6ae0c6`. If it differs, the PRD was edited after this plan was
> written — STOP and report. Also confirm `docs/` and `tools/` do not exist yet
> (`ls docs tools` → "No such file or directory" for both); if either exists, STOP.

## Status

- **Priority**: P1 (blocks every later plan)
- **Effort**: S–M
- **Risk**: LOW (documentation + one stdlib-only check script; no compiler code)
- **Depends on**: none
- **Category**: direction / docs
- **Planned at**: no git repo — PRD `cd project prd.docx` sha256 `8377df6ae0c6…`, 2026-10-10

## Why this matters

The project is a "Compiler Error Assistant" (PRD: `cd project prd.docx`). It adds an AI layer to a course compiler. The layer captures errors per phase (lexical, syntax, semantic), groups cascading errors under one root cause, explains them, and proposes fixes that are verified by re-compiling. The owner has decided that the compiler accepts **exactly one source language: a defined subset of C**, and is **implemented in Python**. Nothing can be built until that subset is written down. The lexer and parser need a grammar, severity tagging needs error codes, the RAG corpus (F7) needs rule names, and personalisation (F9) needs error categories. This plan produces the specification, the error-code catalog, a decision record (ADR), and a checker that keeps the catalog and spec consistent.

A design principle runs through this plan: **every program the subset accepts must also be valid C99.** The subset may reject valid C (unsupported features), and it may be stricter than gcc in a few documented places. It must never accept something real C rejects. This keeps the project honest in its viva and lets later plans cross-check the test corpus against `gcc -std=c99 -fsyntax-only`.

## Current state

- The project root contains `cd project prd.docx` (the PRD), `README.md` (project overview), `VIVA.md` (viva preparation, maintained by the advisor — do not edit either), and `plans/`. There is no code, no `docs/`, no tests, and no git repo.
- PRD facts this plan must honour (quoted):
  - Non-goal: "No support for multiple source languages; one course language only."
  - Non-goal: "Optimization, code generation quality and runtime errors are out of scope." There are three phases only: **lexical, syntax, semantic**.
  - Error record fields: `id`, `phase` (lexical | syntax | semantic), `code` (e.g. `SYN-EXPECTED-TOKEN`), `severity` (fatal | warning), `line`, `column`, `found`, `expected` (list), `snippet`, `root_id`, `rule_ref` ("grammar rule name for RAG lookup").
  - F4: "The label is assigned by the compiler phase and rule, not by the AI."
  - F9 example categories: "missing delimiter, undeclared variable, type mismatch".
  - Tech stack: "Python, hand-written lexer and recursive-descent parser".
- Decisions (record them; do not change them):
  - Source language: **C subset**, file extension `.c`, specified in Step 1.
  - Implementation language: **Python ≥ 3.11** (the dev machine has 3.13.1).
  - Error-code prefixes: `LEX-`, `SYN-`, `SEM-` (fatal semantic) and `WRN-` (semantic warnings).
  - Every `rule_ref` must be a name **defined in the spec**: a rule from an `ebnf` block, or a semantic rule id `sem.<name>`.

## Commands you will need

| Purpose | Command (run from project root) | Expected on success |
|---|---|---|
| Python version | `python --version` | `Python 3.11` or newer |
| Spec/catalog check | `python -I tools/check_spec.py` | `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`, exit 0 |

There is no build, test suite, or linter yet. Do not install anything.

## Scope

**In scope** (create only these files):
- `docs/language-spec.md`
- `docs/error-catalog.md`
- `docs/decisions/0001-single-language-c-subset.md`
- `tools/check_spec.py`
- `plans/README.md` (status row only)

**Out of scope** (do NOT touch):
- `cd project prd.docx`, `README.md` and `VIVA.md`. The owner and advisor maintain them. If you make a decision an examiner might ask about (for example, a deviation from this plan), list it under "Viva notes" in your final report instead of editing `VIVA.md`.
- Any lexer, parser, analyzer, API or UI code.
- Do not run `git init`, create a virtualenv, add `requirements.txt`/`pyproject.toml`, or install packages.
- Do not add C features beyond Step 1. Pointers, structs, unions, enums, typedef, switch, do-while, goto, sizeof, the type qualifiers/modifiers (`long`, `unsigned`, `const`, …), bitwise operators, the ternary operator, array initialiser lists, array parameters, `scanf` and every preprocessor directive except `#include <stdio.h>` are **deliberately unsupported**.

## Steps

### Step 1: Write `docs/language-spec.md`

Create the file with exactly these sections, in this order. Wording may be improved, but **every rule name, token name, `sem.*` id and type rule must appear exactly as written**, because the catalog and the checker reference them. Fence both grammar blocks with exactly ```` ```ebnf ````.

````markdown
# Course C Subset — Language Specification

The compiler accepts one language: a subset of C99. Source files use `.c` and
are UTF-8. The compiler (written in Python) runs three phases — lexical, syntax,
semantic — and produces diagnostics only; nothing is executed or code-generated.

Design rule: every program this compiler accepts is also valid C99. The subset
may reject valid C (features listed in section 6) and is stricter than gcc in
the places marked "stricter than gcc".

## 1. Lexical grammar

```ebnf
token               = IDENT | KEYWORD | UNSUPPORTED_KEYWORD | number | CHAR_LIT
                    | STRING_LIT | OPERATOR | UNSUPPORTED_OP | PUNCT ;
IDENT               = letter , { letter | digit } ;   (* not a keyword *)
letter              = "A".."Z" | "a".."z" | "_" ;
digit               = "0".."9" ;
KEYWORD             = "int" | "float" | "double" | "char" | "void" | "if" | "else"
                    | "while" | "for" | "return" | "break" | "continue" ;
UNSUPPORTED_KEYWORD = "struct" | "union" | "enum" | "typedef" | "switch" | "case"
                    | "default" | "do" | "goto" | "sizeof" | "long" | "short"
                    | "unsigned" | "signed" | "const" | "static" | "extern"
                    | "auto" | "register" | "volatile" ;
number              = INT_LIT | FLOAT_LIT ;
INT_LIT             = digit , { digit } ;
FLOAT_LIT           = digit , { digit } , "." , digit , { digit } ;
CHAR_LIT            = "'" , ( char_char | escape ) , "'" ;   (* exactly one character *)
STRING_LIT          = '"' , { string_char | escape } , '"' ;  (* may not span lines *)
escape              = "\" , ( "n" | "t" | "0" | "'" | '"' | "\" ) ;
OPERATOR            = "+" | "-" | "*" | "/" | "%" | "=" | "+=" | "-=" | "*=" | "/="
                    | "%=" | "++" | "--" | "==" | "!=" | "<" | "<=" | ">" | ">="
                    | "&&" | "||" | "!" ;
UNSUPPORTED_OP      = "&" | "|" | "^" | "~" | "<<" | ">>" | "->" | "." | "?" | ":" ;
PUNCT               = ";" | "," | "(" | ")" | "{" | "}" | "[" | "]" ;
directive           = "#" , { any char except newline } ;
LINE_COMMENT        = "//" , { any char except newline } ;
BLOCK_COMMENT       = "/*" , { any char } , "*/" ;   (* does not nest *)
```

Prose to include: whitespace and comments separate tokens. Lines and columns
are 1-based, and a tab counts as one column. A `directive` must start a line. The only
accepted directive is `#include <stdio.h>` (spaces allowed). The lexer records
that it was seen and does not pass it to the parser. Any other directive is the
error LEX-UNSUPPORTED-DIRECTIVE. Unsupported keywords and operators are
tokenised normally so the parser can report SYN-UNSUPPORTED-FEATURE with a
clear message. Lexical error cases: a character not in any token; a string
not closed before end of line; a char literal that is unclosed, empty, or
holds more than one character; an unclosed block comment; a number followed
directly by a letter, `_` or a second `.` (`12abc`, `1.2.3`, `12.`); an escape
not listed above.

## 2. Syntax grammar

```ebnf
program        = { top_decl } , EOF ;
top_decl       = type_spec , ( function_def | global_decl ) ;
function_def   = IDENT , "(" , params , ")" , ( block | ";" ) ;
params         = [ "void" | param_list ] ;
param_list     = param , { "," , param } ;
param          = type_spec , IDENT ;
global_decl    = declarator , { "," , declarator } , ";" ;
type_spec      = "int" | "float" | "double" | "char" | "void" ;
declarator     = IDENT , [ array_suffix ] , [ "=" , expression ] ;
array_suffix   = "[" , expression , "]" ;
block          = "{" , { statement } , "}" ;
statement      = var_decl | if_stmt | while_stmt | for_stmt | return_stmt
               | break_stmt | continue_stmt | block | expr_stmt | empty_stmt ;
var_decl       = var_core , ";" ;
var_core       = type_spec , declarator , { "," , declarator } ;
if_stmt        = "if" , "(" , expression , ")" , statement , [ "else" , statement ] ;
while_stmt     = "while" , "(" , expression , ")" , statement ;
for_stmt       = "for" , "(" , [ for_init ] , ";" , [ expression ] , ";"
               , [ expression ] , ")" , statement ;
for_init       = var_core | expression ;
return_stmt    = "return" , [ expression ] , ";" ;
break_stmt     = "break" , ";" ;
continue_stmt  = "continue" , ";" ;
expr_stmt      = expression , ";" ;
empty_stmt     = ";" ;
expression     = assignment ;
assignment     = logic_or , [ assign_op , assignment ] ;
assign_op      = "=" | "+=" | "-=" | "*=" | "/=" | "%=" ;
logic_or       = logic_and , { "||" , logic_and } ;
logic_and      = equality , { "&&" , equality } ;
equality       = comparison , { ( "==" | "!=" ) , comparison } ;
comparison     = term , { ( "<" | "<=" | ">" | ">=" ) , term } ;
term           = factor , { ( "+" | "-" ) , factor } ;
factor         = unary , { ( "*" | "/" | "%" ) , unary } ;
unary          = ( "!" | "-" | "+" | "++" | "--" ) , unary | postfix ;
postfix        = primary , { "(" , [ arg_list ] , ")" | "[" , expression , "]" }
               , [ "++" | "--" ] ;
arg_list       = assignment , { "," , assignment } ;
primary        = INT_LIT | FLOAT_LIT | CHAR_LIT | STRING_LIT | IDENT
               | "(" , expression , ")" ;
```

Prose to include:
- `top_decl` chooses `function_def` when the token after `IDENT` is `(`.
- `params` is `void` alone only when the next token is `)`.
- The left side of an `assign_op` and the operand of `++`/`--` must be an lvalue: `IDENT` or `IDENT[expression]`. Anything else is SYN-INVALID-ASSIGN-TARGET.
- `else` binds to the nearest `if`.
- A `*` directly after a `type_spec`, any UNSUPPORTED_KEYWORD and any UNSUPPORTED_OP are reported as SYN-UNSUPPORTED-FEATURE, naming the feature (pointers, structs, …).
- These rule names are the `rule_ref` values for syntax errors.

## 3. Types

- Integer types are `int` and `char`. Floating types are `float` and `double`. `void` is a return type only.
- String literals have no usable type. Their only legal use is as the first argument of `printf`.
- Usual arithmetic conversions: `char` becomes `int`. If either operand is `double`, the result is `double`. Otherwise, if either is `float`, the result is `float`. Otherwise it is `int`.
- `%` and `%=` take integer operands only.
- Comparison, equality, `&&`, `||` and `!` take arithmetic operands and produce `int`.
- Assignment, initialisation, argument passing and return may convert any arithmetic type to any other. A floating value converted to an integer type gives the warning WRN-IMPLICIT-NARROWING.
- Arrays are 1-D. Their element type is int, char, float or double. An array name is not a value: it cannot be assigned, returned or passed.

## 4. Semantic rules

One `###` heading per rule, heading text exactly the id, followed by a 1–3
sentence statement and a 2–5 line C example that violates it:

### sem.declare_before_use
Variables must be declared before use; lookup walks enclosing block scopes,
then file scope. Functions must be declared (prototype or definition) earlier
in the file than any call (C99 rule).
### sem.unique_in_scope
A name may be declared once per scope; shadowing an outer scope is allowed.
Parameters live in the function body's outermost scope; globals and functions
share file scope. Defining a function body twice is a redeclaration.
### sem.function_declarations
A function may have several prototypes and one definition; all must agree on
return type and parameter types.
### sem.type_compat
Operands, initialisers, assignments, arguments and returns must satisfy
section 3.
### sem.no_void_values
No variable or parameter may be void; a call to a void function cannot be
used as a value.
### sem.call_signature
Only functions can be called, with exactly the declared number of arguments,
each convertible to its parameter type.
### sem.return_type
`return expr;` is only allowed in non-void functions and `expr` must convert
to the return type; `return;` only in void functions (stricter than gcc, which
warns).
### sem.return_paths
A non-void function other than `main` should return on every path: the body's
last statement is a `return`, or an `if` with an `else` whose branches both
return on every path (recursively through blocks). Loops never count.
Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly returns 0.
### sem.array_access
An array size must be an integer literal greater than 0 (no variable-length
arrays). Only arrays may be indexed, and the index must have integer type.
Constant out-of-range indices are not checked (runtime behaviour is out of scope).
### sem.loop_control
`break` and `continue` may appear only inside `while` or `for`.
### sem.global_init
A global initialiser must be a numeric or char literal, optionally preceded
by `-`.
### sem.builtins
`printf` is declared only if `#include <stdio.h>` appears before its first
use. Its first argument must be a string literal; further arguments may be any
arithmetic values. Format specifiers are not checked. Redeclaring `printf` is a
redeclaration.
### sem.conditions
Conditions of `if`, `while` and `for` must be arithmetic (any non-zero value
is true). A plain `=` as the outermost operator of a condition produces a
warning, as in gcc's -Wparentheses.
### sem.entry_point
The program must define `int main()` or `int main(void)`. Real C reports a
missing main at link time; this compiler reports it at the end of semantic
analysis.
### sem.unused_declaration
A local variable that is declared but never read produces a warning.
Parameters and globals are exempt.
### sem.unreachable
The first statement after a `return`, `break` or `continue` in the same block
produces one warning. This is a teaching warning that gcc does not emit.

## 5. Example program

Include one valid program of 25–45 lines that uses `#include <stdio.h>`, a
prototype followed by its definition, a global, an array with a `for` loop
using `i++`, `while` with `continue`, `if/else`, `+=`, a nested block with
shadowing, `char` and `double`, and `printf`. Include exactly one implicit
double→int conversion. Label it "valid C99; expected: 0 fatal,
1 warning (WRN-IMPLICIT-NARROWING)".

## 6. Not supported (deliberately)

List the features from the plan's out-of-scope list. For each, give the
message a student will see (SYN-UNSUPPORTED-FEATURE or
LEX-UNSUPPORTED-DIRECTIVE) and one line on why it was cut (scope of a
one-semester project; pointers alone would need a memory model).
````

**Verify**: `grep -c "^### sem\." docs/language-spec.md` → `16`; `grep -c '^```ebnf' docs/language-spec.md` → `2`.

### Step 2: Write `docs/error-catalog.md`

Begin with one paragraph saying this is the single source of truth for error `code`, `phase`, `severity` (PRD F4), F9 `category` and the `rule_ref` used by RAG lookup (F7). Then a **Categories** list containing exactly these ten, each with a one-line meaning:
`malformed-token`, `unclosed-delimiter`, `missing-semicolon`, `syntax-structure`, `undeclared-identifier`, `redeclaration`, `type-mismatch`, `function-misuse`, `control-flow`, `unused-code`.

Then one markdown table with **exactly these 7 columns in this order** and **exactly these 37 rows**. Do not put backticks in the first four columns. Put `rule_ref` in backticks. Do not use the `|` character inside any cell.

| Code | Phase | Severity | Category | rule_ref | Message template | Example trigger |
|---|---|---|---|---|---|---|
| LEX-INVALID-CHAR | lexical | fatal | malformed-token | `token` | Unexpected character '{found}' | `int x = 5 @ 2;` |
| LEX-UNTERMINATED-STRING | lexical | fatal | unclosed-delimiter | `STRING_LIT` | String literal is not closed before end of line | `printf("hi);` |
| LEX-BAD-CHAR-LITERAL | lexical | fatal | malformed-token | `CHAR_LIT` | A char literal must hold exactly one character, e.g. 'a' | `char c = 'ab';` |
| LEX-UNTERMINATED-COMMENT | lexical | fatal | unclosed-delimiter | `BLOCK_COMMENT` | Block comment starting here is never closed with '*/' | `/* note` at end of file |
| LEX-MALFORMED-NUMBER | lexical | fatal | malformed-token | `number` | '{found}' is not a valid number | `int x = 12abc;` |
| LEX-INVALID-ESCAPE | lexical | fatal | malformed-token | `escape` | Unknown escape sequence '{found}' | `printf("a\q");` |
| LEX-UNSUPPORTED-DIRECTIVE | lexical | fatal | syntax-structure | `directive` | Only '#include <stdio.h>' is supported; '{found}' is not | `#define N 10` |
| SYN-MISSING-SEMICOLON | syntax | fatal | missing-semicolon | `<production>` | Expected ';' after {context} but found '{found}' | `int x = 5` then next line |
| SYN-UNBALANCED-BRACKET | syntax | fatal | unclosed-delimiter | `<production>` | Expected '{expected}' to close '{opener}' from line {open_line} but found '{found}' | `if (x > 1 { }` |
| SYN-EXPECTED-TOKEN | syntax | fatal | syntax-structure | `<production>` | Expected {expected} but found '{found}' | `while x > 1) { }` |
| SYN-EXPECTED-EXPRESSION | syntax | fatal | syntax-structure | `<production>` | Expected an expression but found '{found}' | `int x = ;` |
| SYN-EXPECTED-TYPE | syntax | fatal | syntax-structure | `<production>` | Expected a type (int, float, double, char, void) but found '{found}' | `int f(a) { }` |
| SYN-UNEXPECTED-EOF | syntax | fatal | unclosed-delimiter | `<production>` | File ended inside {context}; expected {expected} | `int main() { return 0;` |
| SYN-INVALID-ASSIGN-TARGET | syntax | fatal | syntax-structure | `assignment` | Only a variable or array element can be assigned or incremented | `5 = x;` |
| SYN-UNSUPPORTED-FEATURE | syntax | fatal | syntax-structure | `<production>` | {feature} is not supported in this course's C subset | `int *p;` |
| SEM-UNDECLARED-VAR | semantic | fatal | undeclared-identifier | `sem.declare_before_use` | Variable '{name}' is used before it is declared | `y = 3;` with no `y` |
| SEM-UNDECLARED-FUNC | semantic | fatal | undeclared-identifier | `sem.declare_before_use` | Function '{name}' is not declared before this call | `foo(1);` before `foo` is declared |
| SEM-REDECLARED | semantic | fatal | redeclaration | `sem.unique_in_scope` | '{name}' is already declared in this scope (line {prev_line}) | `int x; int x;` in one block |
| SEM-CONFLICTING-TYPES | semantic | fatal | function-misuse | `sem.function_declarations` | Declarations of '{name}' disagree: {prev_sig} vs {sig} | `int f(int a);` then `float f(int a) {...}` |
| SEM-TYPE-MISMATCH | semantic | fatal | type-mismatch | `sem.type_compat` | Cannot use {found} where {expected} is required | `int x = "hi";` |
| SEM-VOID-VALUE | semantic | fatal | type-mismatch | `sem.no_void_values` | A void value cannot be stored or used in an expression | `int x = log();` where `void log()` |
| SEM-NOT-CALLABLE | semantic | fatal | function-misuse | `sem.call_signature` | '{name}' is not a function | `int x; x(1);` |
| SEM-ARG-COUNT | semantic | fatal | function-misuse | `sem.call_signature` | '{name}' expects {expected} argument(s) but got {found} | `add(1);` for `int add(int a, int b)` |
| SEM-ARG-TYPE | semantic | fatal | function-misuse | `sem.call_signature` | Argument {index} of '{name}' must be {expected} but is {found} | `add(1, "two");` |
| SEM-RETURN-TYPE | semantic | fatal | function-misuse | `sem.return_type` | Function '{name}' returns {expected} but this returns {found} | `return 5;` in `void f()` |
| SEM-NOT-ARRAY | semantic | fatal | type-mismatch | `sem.array_access` | '{name}' is not an array and cannot be indexed | `int x; x[0] = 1;` |
| SEM-INDEX-NOT-INT | semantic | fatal | type-mismatch | `sem.array_access` | Array index must be an integer but has type {found} | `a[1.5] = 2;` |
| SEM-BAD-ARRAY-SIZE | semantic | fatal | type-mismatch | `sem.array_access` | Array size must be an integer literal greater than 0 | `int a[n];` |
| SEM-BREAK-OUTSIDE-LOOP | semantic | fatal | control-flow | `sem.loop_control` | '{found}' can only be used inside a loop | `break;` in `main` body |
| SEM-NONCONST-GLOBAL-INIT | semantic | fatal | syntax-structure | `sem.global_init` | A global variable must be initialised with a literal | `int y = x + 1;` at file scope |
| SEM-PRINTF-FORMAT | semantic | fatal | function-misuse | `sem.builtins` | The first argument of printf must be a string literal | `printf(x);` |
| SEM-MISSING-MAIN | semantic | fatal | control-flow | `sem.entry_point` | Program has no 'int main()' function | file with only `void g() { }` |
| WRN-UNUSED-VAR | semantic | warning | unused-code | `sem.unused_declaration` | Variable '{name}' is declared but never used | `int t = 1;` never read |
| WRN-UNREACHABLE-CODE | semantic | warning | unused-code | `sem.unreachable` | This statement can never run | `return 0; printf("x");` |
| WRN-IMPLICIT-NARROWING | semantic | warning | type-mismatch | `sem.type_compat` | {found} value converted to {expected}; the fractional part is lost | `int n = 2.5;` |
| WRN-MISSING-RETURN | semantic | warning | control-flow | `sem.return_paths` | Function '{name}' may end without returning a value | `int f(int b) { if (b) { return 1; } }` |
| WRN-ASSIGN-IN-CONDITION | semantic | warning | type-mismatch | `sem.conditions` | Assignment used as a condition; did you mean '=='? | `if (x = 5) { }` |

After the table, add **Choosing among syntax codes**. These rules are applied in order when the parser reports an error:
0. The found token is an UNSUPPORTED_KEYWORD or UNSUPPORTED_OP, or is `*` directly after a `type_spec` → `SYN-UNSUPPORTED-FEATURE`.
1. The found token is EOF → `SYN-UNEXPECTED-EOF`.
2. The expected set is exactly `;` → `SYN-MISSING-SEMICOLON`.
3. The expected set contains only closing brackets (`)`, `]`, `}`), or the found token is a closing bracket with no matching opener → `SYN-UNBALANCED-BRACKET`.
4. The parser expected the start of an expression → `SYN-EXPECTED-EXPRESSION`. It expected a type → `SYN-EXPECTED-TYPE`.
5. Otherwise → `SYN-EXPECTED-TOKEN`.

State that for `<production>` rows, the runtime `rule_ref` is the name of the grammar rule (spec section 2) being parsed when the error occurred.

**Verify**: `grep -cE '^\| (LEX|SYN|SEM|WRN)-' docs/error-catalog.md` → `37`.

### Step 3: Write `tools/check_spec.py`

Create this checker, stdlib only. Keep it as written apart from cosmetic formatting:

```python
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
    "control-flow", "unused-code",
}
PREFIX_PHASE = {"LEX": "lexical", "SYN": "syntax", "SEM": "semantic", "WRN": "semantic"}


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
        if re.match(r"^\|\s*(LEX|SYN|SEM|WRN)-", line)
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
        if PREFIX_PHASE[prefix] != phase:
            errors.append(f"{code}: phase {phase} does not match prefix {prefix}")
        if severity != ("warning" if prefix == "WRN" else "fatal"):
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
```

**Verify**: `python -I tools/check_spec.py` → exit 0, output exactly `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`. (54 = 18 lexical + 36 syntax rule names. If you get a different rule count, compare your ebnf blocks with Step 1 rule by rule.)

### Step 4: Write `docs/decisions/0001-single-language-c-subset.md`

Use exactly these five `##` sections: **Status** (Accepted, 2026-10-10), **Context**, **Decision**, **Consequences**, **Still open**.
- Context: PRD open question 1 asked which source language to compile and in what implementation language. The PRD's non-goals require one course language and three phases.
- Decision:
  - The only source language is a C99 subset, specified in `docs/language-spec.md`.
  - Every accepted program is valid C99.
  - The implementation language is Python ≥ 3.11, with a hand-written lexer and recursive-descent parser.
  - Codes are listed in `docs/error-catalog.md`, and `tools/check_spec.py` keeps the spec and catalog consistent.
- Consequences: give the reasons for supporting a single language, one bullet each:
  - Clustering (F2) depends on controlling parser recovery.
  - Per-phase capture (F1) needs our own phases.
  - The RAG corpus (F7) must be small and complete to guarantee correct citations.
  - The fix verifier (F8) re-runs our own pipeline.
  - The scope fits a semester.
  - Also note that the error record will carry a `language` field fixed to `"c"`. A future adapter for another compiler could then add a language without changing the AI layer, but that is not planned.
- Still open: PRD open questions 2–5, and the error-recovery strategy after syntax errors (planned separately).
- End with: "The owner should mark PRD open question 1 as resolved and link this ADR."

**Verify**: `grep -c "^## " docs/decisions/0001-single-language-c-subset.md` → `5`.

### Step 5: Update the index

In `plans/README.md`, set plan 001's status to `DONE`.

**Verify**: `grep "^| 001" plans/README.md` → the row contains `DONE`.

## Test plan

`tools/check_spec.py` is the test. Check that it catches mistakes. Run each mutation, confirm the result, then revert:
1. On the SEM-TYPE-MISMATCH row, change `sem.type_compat` to `sem.type_compatt` → output includes `ERROR: SEM-TYPE-MISMATCH: rule_ref sem.type_compatt has no ...`, exit 1. Revert.
2. On the WRN-UNUSED-VAR row, change `warning` to `fatal` → `ERROR: WRN-UNUSED-VAR: wrong severity fatal`, exit 1. Revert.
3. After reverting both → `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`, exit 0.

## Done criteria

- [ ] `python -I tools/check_spec.py` exits 0 and prints `OK: 37 codes, 54 grammar/lexical rules, 16 semantic rules`
- [ ] `grep -c "^### sem\." docs/language-spec.md` → `16`
- [ ] Both mutation tests failed as expected and were reverted
- [ ] `sha256sum "cd project prd.docx"` still starts with `8377df6ae0c6`
- [ ] `find docs tools -type f` lists exactly the four in-scope files
- [ ] `plans/README.md` row 001 shows `DONE`

## STOP conditions

Stop and report back (do not improvise) if:

- The PRD hash differs, or `docs/` or `tools/` already exists.
- `python --version` is below 3.11.
- The example program in spec section 5 can't be written without an unsupported feature. Report it; do not extend the subset.
- Any rule you are writing would let the compiler accept a program that real C99 rejects. Report the case.
- The checker fails twice on the same row after you fix it. The plan's tables may be inconsistent; report the exact error.

## Maintenance notes

- **Every later plan depends on these docs.** The lexer/parser plan implements sections 1–2 and the syntax-code selection rules. The semantic plan implements sections 3–4. F7 chunks the spec by rule name and `sem.*` id. F9 counts per catalog category.
- The "accepted ⇒ valid C99" rule is testable once the faulty/valid program corpus exists. If `gcc` is available, run `gcc -std=c99 -fsyntax-only` on every program the compiler accepts. Recommend this in the corpus plan.
- Add `python -I tools/check_spec.py` to pytest/CI when they exist.
- Deferred: the error-recovery strategy (sync points, semantic analysis on a partial AST). It decides whether F2's "10+ errors → 1 root cause" target is reachable.
- Deferred: uninitialised-variable warnings (need data-flow analysis) and printf format checking.
