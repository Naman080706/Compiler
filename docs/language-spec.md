# Course C Subset — Language Specification

The compiler accepts one language: course-level C, a subset of C99. Source
files use `.c` and are UTF-8. The compiler (written in Python) runs three
phases — lexical, syntax, semantic — and produces diagnostics only; nothing is
executed or code-generated.

Design rule: every program this compiler accepts is also valid C99. The subset
may reject valid C (features listed in section 6) and is stricter than gcc in
the places marked "stricter than gcc". Programs that use a feature of section 6
(or the user option `--engine gcc`) are handed to the gcc fallback of section 7,
so every C program gets diagnostics.

## 1. Lexical grammar

```ebnf
token               = IDENT | KEYWORD | UNSUPPORTED_KEYWORD | number | CHAR_LIT
                    | STRING_LIT | OPERATOR | UNSUPPORTED_OP | PUNCT ;
IDENT               = letter , { letter | digit } ;   (* not a keyword *)
letter              = "A".."Z" | "a".."z" | "_" ;
digit               = "0".."9" ;
KEYWORD             = "int" | "float" | "double" | "char" | "void" | "long" | "short"
                    | "unsigned" | "signed" | "const" | "static" | "extern"
                    | "struct" | "union" | "enum" | "typedef" | "sizeof"
                    | "if" | "else" | "while" | "for" | "do" | "switch" | "case"
                    | "default" | "return" | "break" | "continue" ;
UNSUPPORTED_KEYWORD = "goto" | "auto" | "register" | "volatile" ;
number              = INT_LIT | FLOAT_LIT ;
INT_LIT             = ( decimal | octal | hex ) , [ int_suffix ] ;
decimal             = digit , { digit } ;
octal               = "0" , { digit } ;
hex                 = "0" , ( "x" | "X" ) , hex_digit , { hex_digit } ;
int_suffix          = ( "u" | "U" ) , [ "l" | "L" | "ll" | "LL" ]
                    | ( "l" | "L" | "ll" | "LL" ) , [ "u" | "U" ] ;
FLOAT_LIT           = digit , { digit } , [ "." , digit , { digit } ] , [ exponent ] , [ "f" | "F" | "l" | "L" ] ;
exponent            = ( "e" | "E" ) , [ "+" | "-" ] , digit , { digit } ;
CHAR_LIT            = "'" , ( char_char | escape ) , "'" ;   (* exactly one character *)
STRING_LIT          = '"' , { string_char | escape } , '"' ;  (* may not span lines *)
escape              = "\" , ( "n" | "t" | "0" | "'" | '"' | "\" ) ;
OPERATOR            = "+" | "-" | "*" | "/" | "%" | "=" | "+=" | "-=" | "*=" | "/="
                    | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" | "++" | "--"
                    | "==" | "!=" | "<" | "<=" | ">" | ">=" | "&&" | "||" | "!"
                    | "&" | "|" | "^" | "~" | "<<" | ">>" | "->" | "." | "?" | ":" ;
UNSUPPORTED_OP      = "..." ;
PUNCT               = ";" | "," | "(" | ")" | "{" | "}" | "[" | "]" ;
directive           = "#" , { any char except newline } ;
LINE_COMMENT        = "//" , { any char except newline } ;
BLOCK_COMMENT       = "/*" , { any char } , "*/" ;   (* does not nest *)
```

Whitespace and comments separate tokens. Lines and columns are 1-based, and a
tab counts as one column. A `directive` must start a line. The accepted
directives are:

- `#include <H>` where `H` is `stdio.h`, `stdlib.h`, `string.h`, `math.h`,
  `ctype.h` or `stdbool.h` (spaces allowed). The lexer records the header and its
  position and does not pass the directive to the parser.
- `#define NAME value`, an object-like macro. The lexer replaces every later
  use of `NAME` by the tokens of `value` (simple substitution; the replacement
  tokens take the position of the use). `value` may be empty or use macros
  defined before it.

Any other directive (`#include "file.h"`, another header, a function-like macro
`#define F(x) ...`, `#undef`, `#if`, `#ifdef`, `#pragma`, ...) is the error
LEX-UNSUPPORTED-DIRECTIVE.

Unsupported keywords and operators are tokenised normally so the parser can
report SYN-UNSUPPORTED-FEATURE with a clear message.

Lexical error cases:
- a character that is not part of any token;
- a string not closed before the end of the line;
- a char literal that is unclosed, empty, or holds more than one character;
- an unclosed block comment;
- a number followed directly by a letter, `_` or a second `.` (`12abc`, `1.2.3`, `12.`);
- an escape sequence not listed in `escape`.

## 2. Syntax grammar

```ebnf
program        = { top_decl } , EOF ;
top_decl       = type_spec , ( function_def | global_decl ) ;
function_def   = { "*" } , IDENT , "(" , params , ")" , ( block | ";" ) ;
params         = [ "void" | param_list ] ;
param_list     = param , { "," , param } ;
param          = type_spec , { "*" } , [ IDENT ] , { "[" , [ assignment ] , "]" } ;
global_decl    = [ declarator , { "," , declarator } ] , ";" ;
type_spec      = { "const" | "static" | "extern" | "typedef" } ,
                 ( basic_type | struct_spec | enum_spec | TYPEDEF_NAME ) ,
                 { "const" | "static" | "extern" | "typedef" } ;
basic_type     = { "unsigned" | "signed" | "long" | "short" | "int" | "char" | "float" | "double" | "void" } ;
struct_spec    = ( "struct" | "union" ) , ( IDENT | [ IDENT ] , "{" , member_decl , { member_decl } , "}" ) ;
member_decl    = type_spec , [ member , { "," , member } ] , ";" ;
member         = { "*" } , IDENT , { "[" , assignment , "]" } ;
enum_spec      = "enum" , ( IDENT | [ IDENT ] , "{" , IDENT , [ "=" , assignment ]
                 , { "," , IDENT , [ "=" , assignment ] } , [ "," ] , "}" ) ;
declarator     = { "*" , { "const" } } , IDENT , { array_suffix } , [ "=" , initializer ] ;
array_suffix   = "[" , [ assignment ] , "]" ;
initializer    = assignment | init_list ;
init_list      = "{" , initializer , { "," , initializer } , [ "," ] , "}" ;
block          = "{" , { statement } , "}" ;
statement      = var_decl | if_stmt | while_stmt | do_while_stmt | for_stmt | switch_stmt
               | case_label | default_label | return_stmt | break_stmt | continue_stmt
               | block | expr_stmt | empty_stmt ;
var_decl       = var_core , ";" ;
var_core       = type_spec , [ declarator , { "," , declarator } ] ;
if_stmt        = "if" , "(" , expression , ")" , statement , [ "else" , statement ] ;
while_stmt     = "while" , "(" , expression , ")" , statement ;
do_while_stmt  = "do" , statement , "while" , "(" , expression , ")" , ";" ;
for_stmt       = "for" , "(" , [ for_init ] , ";" , [ expression ] , ";"
               , [ expression ] , ")" , statement ;
for_init       = var_core | expression ;
switch_stmt    = "switch" , "(" , expression , ")" , statement ;
case_label     = "case" , conditional , ":" ;
default_label  = "default" , ":" ;
return_stmt    = "return" , [ expression ] , ";" ;
break_stmt     = "break" , ";" ;
continue_stmt  = "continue" , ";" ;
expr_stmt      = expression , ";" ;
empty_stmt     = ";" ;
expression     = assignment , { "," , assignment } ;
assignment     = conditional , [ assign_op , assignment ] ;
assign_op      = "=" | "+=" | "-=" | "*=" | "/=" | "%=" | "&=" | "|=" | "^=" | "<<=" | ">>=" ;
conditional    = logic_or , [ "?" , expression , ":" , conditional ] ;
logic_or       = logic_and , { "||" , logic_and } ;
logic_and      = bit_or , { "&&" , bit_or } ;
bit_or         = bit_xor , { "|" , bit_xor } ;
bit_xor        = bit_and , { "^" , bit_and } ;
bit_and        = equality , { "&" , equality } ;
equality       = comparison , { ( "==" | "!=" ) , comparison } ;
comparison     = shift , { ( "<" | "<=" | ">" | ">=" ) , shift } ;
shift          = term , { ( "<<" | ">>" ) , term } ;
term           = factor , { ( "+" | "-" ) , factor } ;
factor         = unary , { ( "*" | "/" | "%" ) , unary } ;
unary          = ( "!" | "-" | "+" | "~" | "*" | "&" | "++" | "--" ) , unary
               | sizeof_expr | cast | postfix ;
sizeof_expr    = "sizeof" , ( "(" , type_name , ")" | unary ) ;
cast           = "(" , type_name , ")" , unary ;
type_name      = type_spec , { "*" } , { "[" , assignment , "]" } ;
postfix        = primary , { "(" , [ arg_list ] , ")" | "[" , expression , "]"
               | ( "." | "->" ) , IDENT } , [ "++" | "--" ] ;
arg_list       = assignment , { "," , assignment } ;
primary        = INT_LIT | FLOAT_LIT | CHAR_LIT | STRING_LIT , { STRING_LIT } | IDENT
               | "(" , expression , ")" ;
```

- `top_decl` chooses `function_def` when, after the stars, the token after `IDENT` is `(`.
- `params` is `void` alone only when the next token is `)`. A parameter may omit its name in a prototype; a definition needs every name. An array parameter is a pointer.
- `TYPEDEF_NAME` is an `IDENT` that an earlier `typedef` declared (or `size_t`, `FILE`, `bool` once their header is included). `typedef` as a specifier makes the declarators typedef names instead of variables.
- `basic_type` keywords combine as in C: `unsigned` alone is `unsigned int`; `long long`, `unsigned char`, `long double`, `short int` are valid; `short long` or `float long` are not.
- `case_label` and `default_label` are markers inside a switch body, not wrappers around the next statement.
- The left side of an `assign_op` and the operand of `++`/`--` must be an lvalue: `IDENT`, `a[i]`, `s.m`, `p->m` or `*p`. Anything else (a parenthesised variable, a call, a literal, ...) is SYN-INVALID-ASSIGN-TARGET.
- `else` binds to the nearest `if`. Adjacent `STRING_LIT`s are one string.
- In an `expression` the comma operator is allowed; in `arg_list`, `initializer`, `array_suffix` and `case_label` a comma separates items instead.
- `(` followed by a `type_spec` starts a `cast`; `sizeof` of a type needs the parentheses.
- Still unsupported (SYN-UNSUPPORTED-FEATURE, naming the feature): `goto`, `auto`, `register`, `volatile`, labels (`name:`), function pointers (`(*f)(...)` in a declarator), variadic parameters (`...`), bit-fields (`int x : 3;`), designated initialisers (`{.x = 1}`), and impossible type-keyword combinations.
- These rule names are the `rule_ref` values for syntax errors.

## 3. Types

- Integer types: `char`, `signed char`, `unsigned char`, `short`, `int`, `long`, `long long` (each also `unsigned`), `_Bool` (spelled `bool` with `<stdbool.h>`), and every `enum` type. Floating types: `float`, `double`, `long double`. `void` has no values: it is a return type, a pointer base (`void *`) or a parameter list `(void)`.
- Derived types: pointers (`T *`), arrays (`T[N]`, also multi-dimensional), `struct` and `union` types, and functions. Function pointers do not exist in the subset.
- A string literal has type `char[N]` and decays like any array. It may initialise a `char` array or be passed or assigned as a `char *` or `const char *`.
- An array name decays to a pointer to its first element in every value context except `sizeof`, `&` and an array initialiser. An array parameter is a pointer.
- `NULL` (from `<stdio.h>`, `<stdlib.h>` or `<string.h>`) and the integer constant `0` are null pointer constants.
- Usual arithmetic conversions: integers smaller than `int` become `int`; if either operand is `long double`, `double` or `float` the result is that floating type, in that order; otherwise the larger integer rank wins, and `unsigned` wins at equal rank.
- `%`, `<<`, `>>`, `&`, `|`, `^`, `~` and their assignment forms take integer operands only.
- Comparison, equality, `&&`, `||` and `!` take scalar operands (numbers or pointers) and produce `int`.
- Pointer arithmetic: `pointer + integer`, `integer + pointer`, `pointer - integer` give a pointer; `pointer - pointer` gives `long`; two pointers (or a pointer and a null pointer constant) compare with `==`, `!=`, `<`, ...; `pointer += integer` and `pointer -= integer` are allowed.
- Assignment, initialisation, argument passing and return may convert any arithmetic type to any other. A floating value converted to an integer type gives the warning WRN-IMPLICIT-NARROWING. A pointer converts to a pointer of the same base type (ignoring `const` and, between integer bases, signedness) and to or from `void *`; any other pointer conversion is the warning WRN-INCOMPATIBLE-POINTER. A number other than a null pointer constant does not convert to a pointer, and a pointer does not convert to a number (both stricter than gcc, which only warns).
- Structs and unions are assigned, passed and returned whole when both sides have the same type. An initialiser list `{...}` initialises an array element by element and a struct member by member (extra braces and braces left out are accepted).
- `const` makes the variable or the pointed-to value read-only (`const int n`, `const char *s`, `char *const p`).

## 4. Semantic rules

Each rule below has a statement and a C example that violates it.

### sem.declare_before_use
Variables must be declared before use; lookup walks enclosing block scopes,
then file scope. Functions must be declared (prototype or definition) earlier
in the file than any call (C99 rule).

```c
int main(void) {
    y = 3;          /* y was never declared */
    foo(1);         /* foo was never declared */
    return 0;
}
```

### sem.unique_in_scope
A name may be declared once per scope; shadowing an outer scope is allowed.
Parameters live in the function body's outermost scope; globals and functions
share file scope. Defining a function body twice is a redeclaration.

```c
int main(void) {
    int x = 1;
    int x = 2;      /* x is already declared in this scope */
    return x;
}
```

### sem.function_declarations
A function may have several prototypes and one definition; all must agree on
return type and parameter types.

```c
int f(int a);
float f(int a) {    /* return type disagrees with the prototype */
    return 1.0;
}
```

### sem.type_compat
Operands, initialisers, assignments, arguments and returns must satisfy
section 3.

```c
int main(void) {
    int x = "hi";       /* a string literal is not an arithmetic value */
    int r = 7.5 % 2;    /* % needs integer operands */
    return 0;
}
```

### sem.no_void_values
No variable or parameter may be plain `void` (a `void *` is fine); a call to a
void function cannot be used as a value.

```c
void log_it(void) { }
int main(void) {
    int x = log_it();   /* log_it returns no value */
    return 0;
}
```

### sem.call_signature
Only functions can be called, with exactly the declared number of arguments,
each convertible to its parameter type.

```c
int add(int a, int b) { return a + b; }
int main(void) {
    int x = 0;
    x(1);               /* x is not a function */
    return add(1);      /* add expects 2 arguments */
}
```

### sem.return_type
`return expr;` is only allowed in non-void functions and `expr` must convert
to the return type; `return;` only in void functions (stricter than gcc, which
warns).

```c
void f(void) {
    return 5;       /* void function returns a value */
}
int g(void) {
    return;         /* non-void function returns nothing */
}
```

### sem.return_paths
A non-void function other than `main` should return on every path. A
statement returns on every path if it is a `return`, a block in which ANY
statement returns on every path, or an `if` with an `else` whose two branches
both return on every path. Loops never count. Statements that follow a
statement which returns on every path, in the same block, can never run: the
first of them gets WRN-UNREACHABLE-CODE (`sem.unreachable`), not a missing
return. Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly
returns 0.

```c
int f(int b) {
    if (b) {
        return 1;
    }                   /* no return when b is 0 */
}
```

### sem.array_access
An array size must be a constant integer expression greater than 0: a literal,
an enum constant, a `#define`d number, `sizeof`, or arithmetic on those (no
variable-length arrays). Only the first size may be left out, and only when an
initialiser gives it. Only arrays and pointers may be indexed, and the index must
have integer type. Constant out-of-range indices are not checked (runtime
behaviour is out of scope).

```c
int main(void) {
    int n = 3;
    int a[n];           /* size must be constant */
    int x = 1;
    x[0] = 1;           /* x is not an array or pointer */
    return 0;
}
```

### sem.loop_control
`break` may appear only inside a loop (`while`, `do`, `for`) or a `switch`;
`continue` only inside a loop.

```c
int main(void) {
    break;              /* not inside a loop */
    return 0;
}
```

### sem.global_init
A global (or `static`) initialiser must be a constant expression: literals, enum
constants, `sizeof`, arithmetic on those, string literals, `NULL`, `&global`, the
name of a global array or function, or a `{...}` list of such items. Other
variables are not constants.

```c
int x = 4;
int y = x + 1;          /* not a literal */
```

### sem.builtins
The common functions of a supported header are declared only if its `#include`
appears before their first use: `<stdio.h>` (`printf`, `scanf`, `sprintf`, `puts`,
`getchar`, `fopen`, ...; `NULL`, `EOF`, `FILE`, `size_t`), `<stdlib.h>` (`malloc`,
`calloc`, `realloc`, `free`, `exit`, `abs`, `atoi`, `rand`, ...), `<string.h>`
(`strlen`, `strcpy`, `strcmp`, `strcat`, `memset`, `memcpy`, ...), `<math.h>`
(`sqrt`, `pow`, `fabs`, `floor`, `ceil`, `sin`, `cos`, ...), `<ctype.h>`
(`isalpha`, `isdigit`, `toupper`, ...) and `<stdbool.h>` (`bool`, `true`,
`false`). Their parameter types are checked like any function's; `printf`,
`scanf` and the other variadic functions accept further arguments of any number
or pointer type. The first argument of `printf` must be a string: a string
literal, a `char` array or a `char` pointer. Format specifiers are not checked.
Redeclaring a builtin function is a redeclaration.

```c
#include <stdio.h>
int main(void) {
    int x = 1;
    printf(x);          /* first argument must be a string literal */
    return 0;
}
```

### sem.conditions
Conditions of `if`, `while`, `do` and `for` must be scalar: a number or a
pointer (any non-zero value or non-null pointer is true). A plain `=` as the outermost operator of a condition produces a
warning, as in gcc's -Wparentheses.

```c
int main(void) {
    int x = 0;
    if (x = 5) {        /* assignment, probably meant == */
        x = 1;
    }
    return x;
}
```

### sem.entry_point
The program must define `int main()`, `int main(void)` or
`int main(int argc, char *argv[])`. Real C reports a
missing main at link time; this compiler reports it at the end of semantic
analysis.

```c
void g(void) { }        /* the file has no main */
```

### sem.pointers
`*p` needs a pointer (or array) operand, and `&x` needs an lvalue: a variable,
an array element, a struct member or a dereference. Dereferencing a non-pointer
is an error. Taking the address of a value that is not stored anywhere (`&5`,
`&(a + b)`, `&f()`) is an error. A pointer assigned, initialised, passed or
returned as a pointer to a different base type (`int *p = &some_double;`) gives
the warning WRN-INCOMPATIBLE-POINTER, as in gcc; `void *` converts to and from
any object pointer.

```c
int main(void) {
    int x = 1;
    double d = 2.0;
    int *p = &d;        /* warning: incompatible pointer types */
    *x = 2;             /* x is not a pointer */
    int *q = &(x + 1);  /* x + 1 has no address */
    return 0;
}
```

### sem.members
`s.m` needs a struct or union value and `p->m` a pointer to one; the member must
exist. Using `.` on a pointer, `->` on a struct value, or either on any other
type is an error. A struct that is only declared (`struct Node;`) is incomplete:
a variable or member of that type, or a member access through it, is an error
(a pointer to it is fine).

```c
struct Point { int x; int y; };
int main(void) {
    struct Point p;
    int n = 1;
    p.z = 3;            /* Point has no member z */
    n.x = 1;            /* n is not a struct */
    p->x = 2;           /* p is not a pointer */
    return 0;
}
```

### sem.const_correctness
A `const` variable, an element of a `const` array, and the value a
`const T *` points to cannot be assigned to, incremented, or decremented.

```c
int main(void) {
    const int limit = 10;
    limit = 20;         /* limit is const */
    return 0;
}
```

### sem.switch_stmt
The expression of a `switch` must have integer type. Each `case` label must be
an integer constant expression (a literal, a character, an enum constant, or
arithmetic on those), and no two labels of one switch may have the same value;
a switch has at most one `default`. `case` and `default` may appear only inside
a switch.

```c
int main(void) {
    int n = 2;
    int k = 1;
    switch (n) {
        case 1: n = 5; break;
        case 1: n = 6; break;   /* duplicate label */
        case k: n = 7; break;   /* not a constant */
    }
    return 0;
}
```

### sem.gcc_fallback
Diagnostics that come from the gcc fallback (section 7) are not checked by any
rule of this language: their text is gcc's own. They carry the rule name
`sem.gcc_fallback` so the assistant can say where they came from.

```c
int main(void) {
    goto done;          /* goto is outside the subset: gcc reports on this program */
done:
    return 0;
}
```

### sem.unused_declaration
A local variable that is declared but never read produces a warning.
Assigning with `=` is not a read. Compound assignment (`+=` and the like) and
`++`/`--` both read and write. Parameters and globals are exempt.

```c
int main(void) {
    int t = 1;          /* t is never read */
    return 0;
}
```

### sem.unreachable
The first statement after a `break`, a `continue`, or any statement that
returns on every path (a `return`, a block containing one, or an `if`/`else`
whose branches both return on every path; see `sem.return_paths`) in the same
block produces one warning. This is a teaching warning that gcc does not emit.

```c
int main(void) {
    return 0;
    return 1;           /* can never run */
}
```

## 5. Example program

Valid C99; expected: 0 fatal, 1 warning (WRN-IMPLICIT-NARROWING, at the line
`int scaled = ratio * 2;`, where a double is converted to int).

```c
#include <stdio.h>

int total = 0;

int square(int n);

int square(int n) {
    return n * n;
}

int main(void) {
    int data[5];
    int i;
    char grade = 'A';
    double ratio = 2.5;
    int scaled = ratio * 2;

    for (i = 0; i < 5; i++) {
        data[i] = square(i);
    }
    i = 0;
    while (i < 5) {
        i++;
        if (data[i - 1] % 2 == 0) {
            continue;
        } else {
            total += data[i - 1];
        }
    }
    {
        int total = scaled;
        printf("inner total: %d\n", total);
    }
    printf("grade %c, outer total %d\n", grade, total);
    return 0;
}
```

## 6. Not supported (deliberately)

Each feature below is rejected with the message a student will see. All were
cut for the same reason: the project is a one-semester effort, and each
feature adds grammar, types or runtime concepts that are not needed to study
compiler error handling. A program that uses one of them is analysed by the gcc
fallback instead (section 7), so the student still gets diagnostics.

| Feature | Message the student sees | Why it was cut |
|---|---|---|
| Function pointers (`int (*f)(int)`, `typedef int (*fn)(int)`, passing a function as an argument, `qsort`) | SYN-UNSUPPORTED-FEATURE: Function pointers is not supported in this course's C subset | They need a function-type grammar and indirect calls. |
| Variadic function definitions (`int f(int n, ...)`) | SYN-UNSUPPORTED-FEATURE: Variadic functions ('...') is not supported in this course's C subset | They need `<stdarg.h>`. |
| Bit-fields (`int flag : 1;`) | SYN-UNSUPPORTED-FEATURE: Bit-fields is not supported in this course's C subset | They need layout rules. |
| `goto` and labels | SYN-UNSUPPORTED-FEATURE: 'goto' (Labels (goto targets)) is not supported in this course's C subset | Unstructured jumps are outside the control-flow error classes studied. |
| `auto`, `register`, `volatile` | SYN-UNSUPPORTED-FEATURE: 'register' is not supported in this course's C subset | Storage hints with no effect on diagnostics. |
| Designated initialisers (`{.x = 1}`), compound literals | SYN-UNSUPPORTED-FEATURE: Designated initialisers is not supported in this course's C subset | They need member lookup inside an initialiser. |
| Function-like macros (`#define SQ(x) ((x)*(x))`), `#undef`, `#if`, `#ifdef`, `#ifndef`, `#pragma`, `#include "file.h"`, headers other than the six supported | LEX-UNSUPPORTED-DIRECTIVE: '#ifdef DEBUG' is not supported; ... | A preprocessor is a separate language and a separate project. |

## 7. The gcc fallback

The compiler of sections 1-4 is the primary engine (`engine: "cea"`). The gcc
fallback (`src/cea/gcc_fallback.py`, `engine: "gcc"`) runs
`gcc -std=c99 -Wall -fsyntax-only -fdiagnostics-format=json` on the source when

- the primary engine reported SYN-UNSUPPORTED-FEATURE or LEX-UNSUPPORTED-DIRECTIVE
  (the program uses a feature of section 6), or
- the user asked for it with `--engine gcc` (CLI) or `"engine": "gcc"` (API).

Every gcc diagnostic becomes an error record with the code `GCC-ERROR`,
`GCC-WARNING` or `GCC-NOTE`, gcc's line and column, and gcc's message. A `note`
(either a child of a diagnostic or a separate `note:` line) is linked to the
diagnostic it follows with `caused_by`, so clustering shows it as a symptom of
that diagnostic. If gcc is not installed the primary engine's own result is
returned together with a message that says so.

The `phase` of a gcc record is guessed from the message text, in this order:

1. lexical: the message mentions a stray character, an unterminated string,
   character constant or comment, an invalid number or suffix, an unknown
   escape sequence, an empty character constant, or "missing terminating";
2. syntax: the message starts with `expected`, or mentions `parse error`,
   `before '...' token`, `stray`, `unbalanced`, "at end of input", "unknown type
   name", "invalid preprocessing directive", or "#include expects";
3. semantic: everything else (undeclared, redefinition, incompatible types, ...).

