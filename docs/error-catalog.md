# Error Catalog

This file is the single source of truth for every diagnostic the compiler can emit. For each one it fixes the error `code`, the `phase`, the `severity` (PRD F4: the label comes from the compiler phase and rule, never from the AI), the F9 personalisation `category`, and the `rule_ref` used for RAG lookup (F7). Every `rule_ref` is a rule name defined in `docs/language-spec.md`: a rule from an `ebnf` block, or a semantic rule id `sem.<name>`. `tools/check_spec.py` keeps the two files consistent.

## Categories

- `malformed-token`: a token is spelled wrongly (bad character, number, escape or char literal).
- `unclosed-delimiter`: a string, comment or bracket is opened and never closed.
- `missing-semicolon`: a `;` is missing where a statement or declaration ends.
- `syntax-structure`: the program shape is wrong (unexpected token, missing expression or type, unsupported construct).
- `undeclared-identifier`: a variable or function is used without a prior declaration.
- `redeclaration`: a name is declared more than once in the same scope.
- `type-mismatch`: a value of the wrong type is used, or a conversion loses information.
- `function-misuse`: a function is declared, called or returned from incorrectly.
- `control-flow`: `break`, `continue`, `return` paths or `main` are used incorrectly.
- `unused-code`: code that is declared or written but never has any effect.

## Codes

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

For rows whose `rule_ref` is `<production>`, the runtime `rule_ref` is the name of the grammar rule (spec section 2) being parsed when the error occurred.

## Choosing among syntax codes

These rules are applied in order when the parser reports an error:

0. The found token is an UNSUPPORTED_KEYWORD or UNSUPPORTED_OP, or is `*` directly after a `type_spec` → `SYN-UNSUPPORTED-FEATURE`.
1. The found token is EOF → `SYN-UNEXPECTED-EOF`.
2. The expected set is exactly `;` → `SYN-MISSING-SEMICOLON`.
3. The expected set contains only closing brackets (`)`, `]`, `}`), or the found token is a closing bracket with no matching opener → `SYN-UNBALANCED-BRACKET`.
4. The parser expected the start of an expression → `SYN-EXPECTED-EXPRESSION`. It expected a type → `SYN-EXPECTED-TYPE`.
5. Otherwise → `SYN-EXPECTED-TOKEN`.
