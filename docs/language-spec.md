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

Whitespace and comments separate tokens. Lines and columns are 1-based, and a
tab counts as one column. A `directive` must start a line. The only accepted
directive is `#include <stdio.h>` (spaces allowed). The lexer records that it
was seen and does not pass it to the parser. Any other directive is the error
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

- `top_decl` chooses `function_def` when the token after `IDENT` is `(`.
- `params` is `void` alone only when the next token is `)`.
- The left side of an `assign_op` and the operand of `++`/`--` must be an lvalue: `IDENT` or `IDENT[expression]`. Anything else is SYN-INVALID-ASSIGN-TARGET.
- `else` binds to the nearest `if`.
- A `*` directly after a `type_spec`, any UNSUPPORTED_KEYWORD and any UNSUPPORTED_OP are reported as SYN-UNSUPPORTED-FEATURE, naming the feature (pointers, structs, and so on).
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
No variable or parameter may be void; a call to a void function cannot be
used as a value.

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
A non-void function other than `main` should return on every path: the body's
last statement is a `return`, or an `if` with an `else` whose branches both
return on every path (recursively through blocks). Loops never count.
Violation is a warning, as in gcc's -Wreturn-type. `main` implicitly returns 0.

```c
int f(int b) {
    if (b) {
        return 1;
    }                   /* no return when b is 0 */
}
```

### sem.array_access
An array size must be an integer literal greater than 0 (no variable-length
arrays). Only arrays may be indexed, and the index must have integer type.
Constant out-of-range indices are not checked (runtime behaviour is out of scope).

```c
int main(void) {
    int n = 3;
    int a[n];           /* size must be a literal */
    int x = 1;
    x[0] = 1;           /* x is not an array */
    return 0;
}
```

### sem.loop_control
`break` and `continue` may appear only inside `while` or `for`.

```c
int main(void) {
    break;              /* not inside a loop */
    return 0;
}
```

### sem.global_init
A global initialiser must be a numeric or char literal, optionally preceded
by `-`.

```c
int x = 4;
int y = x + 1;          /* not a literal */
```

### sem.builtins
`printf` is declared only if `#include <stdio.h>` appears before its first
use. Its first argument must be a string literal; further arguments may be any
arithmetic values. Format specifiers are not checked. Redeclaring `printf` is a
redeclaration.

```c
#include <stdio.h>
int main(void) {
    int x = 1;
    printf(x);          /* first argument must be a string literal */
    return 0;
}
```

### sem.conditions
Conditions of `if`, `while` and `for` must be arithmetic (any non-zero value
is true). A plain `=` as the outermost operator of a condition produces a
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
The program must define `int main()` or `int main(void)`. Real C reports a
missing main at link time; this compiler reports it at the end of semantic
analysis.

```c
void g(void) { }        /* the file has no main */
```

### sem.unused_declaration
A local variable that is declared but never read produces a warning.
Parameters and globals are exempt.

```c
int main(void) {
    int t = 1;          /* t is never read */
    return 0;
}
```

### sem.unreachable
The first statement after a `return`, `break` or `continue` in the same block
produces one warning. This is a teaching warning that gcc does not emit.

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
compiler error handling.

| Feature | Message the student sees | Why it was cut |
|---|---|---|
| Pointers (`int *p;`, address-of `&x`) | SYN-UNSUPPORTED-FEATURE: pointers are not supported in this course's C subset | Pointers alone would need a memory model and a larger type system. |
| `struct`, `union`, `enum`, `typedef` | SYN-UNSUPPORTED-FEATURE: structs (unions, enums, typedef) are not supported in this course's C subset | User-defined types need type tables and member access rules. |
| `switch`, `case`, `default`, `do`, `goto` | SYN-UNSUPPORTED-FEATURE: switch (do-while, goto) is not supported in this course's C subset | `if`, `while` and `for` already cover the control-flow error classes. |
| `sizeof` | SYN-UNSUPPORTED-FEATURE: sizeof is not supported in this course's C subset | Needs type sizes and a type-expression grammar. |
| `long`, `short`, `unsigned`, `signed` | SYN-UNSUPPORTED-FEATURE: integer type modifiers are not supported in this course's C subset | Multiplies the conversion rules without adding new error kinds. |
| `const`, `static`, `extern`, `auto`, `register`, `volatile` | SYN-UNSUPPORTED-FEATURE: storage classes and qualifiers are not supported in this course's C subset | Needs linkage and const-correctness rules. |
| Bitwise operators (and, or, xor, not, shifts), ternary `? :`, `.` and `->` | SYN-UNSUPPORTED-FEATURE: this operator is not supported in this course's C subset | More precedence levels and member access; little extra teaching value. |
| Array initialiser lists, array parameters | SYN-UNSUPPORTED-FEATURE or SYN-EXPECTED-TOKEN at the `{` or `[` | Need initialiser typing and array-to-pointer decay. |
| `scanf` and any header other than `<stdio.h>` | SEM-UNDECLARED-FUNC for `scanf` (its `&x` argument is already SYN-UNSUPPORTED-FEATURE) | Input needs pointers, which are unsupported. |
| Preprocessor directives other than `#include <stdio.h>` (`#define`, `#if`, and so on) | LEX-UNSUPPORTED-DIRECTIVE: Only '#include <stdio.h>' is supported | A preprocessor is a separate language and a separate project. |
