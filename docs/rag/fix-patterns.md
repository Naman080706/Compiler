<!-- Curated common mistakes and fixes for F7 RAG grounding: one chunk per catalog code. -->
# RAG corpus: fix patterns

## fix: LEX-INVALID-CHAR
code: LEX-INVALID-CHAR
phase: lexical
rule_ref: token
mistake: Typing a character that is not part of the subset, such as @, $ or a stray backtick, often by pasting from a document.
fix: Delete the character, or replace it with the intended operator or punctuation.

## fix: LEX-UNTERMINATED-STRING
code: LEX-UNTERMINATED-STRING
phase: lexical
rule_ref: STRING_LIT
mistake: Forgetting the closing double quote of a string, as in printf("hi);
fix: Add the closing " before the ) so the string ends on the same line.

## fix: LEX-BAD-CHAR-LITERAL
code: LEX-BAD-CHAR-LITERAL
phase: lexical
rule_ref: CHAR_LIT
mistake: Putting several characters between single quotes, as in 'ab', or using single quotes for a word.
fix: Use one character in single quotes ('a'), or double quotes for a string ("ab").

## fix: LEX-UNTERMINATED-COMMENT
code: LEX-UNTERMINATED-COMMENT
phase: lexical
rule_ref: BLOCK_COMMENT
mistake: Starting a /* comment and never writing the closing */.
fix: Add */ where the comment should end, or use // for a one-line comment.

## fix: LEX-MALFORMED-NUMBER
code: LEX-MALFORMED-NUMBER
phase: lexical
rule_ref: number
mistake: Letters stuck to digits, as in 12abc, or a number with two decimal points.
fix: Write a plain integer or decimal such as 12 or 1.5; put a space or operator between a number and a name.

## fix: LEX-INVALID-ESCAPE
code: LEX-INVALID-ESCAPE
phase: lexical
rule_ref: escape
mistake: Using a backslash escape the language does not know, such as \q in a string.
fix: Use a supported escape (\n, \t, \\, \", \') or remove the backslash.

## fix: LEX-UNSUPPORTED-DIRECTIVE
code: LEX-UNSUPPORTED-DIRECTIVE
phase: lexical
rule_ref: directive
mistake: Using #define or another preprocessor directive.
fix: Keep only #include <stdio.h>; replace a #define constant with a global variable or a literal.

## fix: SYN-MISSING-SEMICOLON
code: SYN-MISSING-SEMICOLON
phase: syntax
rule_ref: <production>
mistake: Ending a declaration, assignment, return or call statement without a semicolon, usually at the end of a line.
fix: Add ; at the end of the statement the error points after.

## fix: SYN-UNBALANCED-BRACKET
code: SYN-UNBALANCED-BRACKET
phase: syntax
rule_ref: <production>
mistake: Opening ( [ or { and not closing it, or closing a different kind of bracket, as in if (x > 1 { }.
fix: Add or correct the matching closing bracket so every opener is closed in the right order.

## fix: SYN-EXPECTED-TOKEN
code: SYN-EXPECTED-TOKEN
phase: syntax
rule_ref: <production>
mistake: Leaving out a required token, such as the ( before a while condition or the ) after it.
fix: Insert the token the message says was expected at the reported position.

## fix: SYN-EXPECTED-EXPRESSION
code: SYN-EXPECTED-EXPRESSION
phase: syntax
rule_ref: <production>
mistake: Leaving the value out of an assignment or condition, as in int x = ;.
fix: Write an expression (a literal, a variable or a calculation) where the error points.

## fix: SYN-EXPECTED-TYPE
code: SYN-EXPECTED-TYPE
phase: syntax
rule_ref: <production>
mistake: Writing a parameter or declaration without a type, as in int f(a).
fix: Put one of int, float, double, char or void before the name.

## fix: SYN-UNEXPECTED-EOF
code: SYN-UNEXPECTED-EOF
phase: syntax
rule_ref: <production>
mistake: Reaching the end of the file while a block, parenthesis or statement is still open, often a missing closing }.
fix: Add the missing closing bracket or token before the end of the file.

## fix: SYN-INVALID-ASSIGN-TARGET
code: SYN-INVALID-ASSIGN-TARGET
phase: syntax
rule_ref: assignment
mistake: Assigning to something that is not a variable or array element, as in 5 = x; or a + b = c;.
fix: Put a variable name or an array element such as a[i] on the left of the =, and the value on the right.

## fix: SYN-UNSUPPORTED-FEATURE
code: SYN-UNSUPPORTED-FEATURE
phase: syntax
rule_ref: <production>
mistake: Using a C feature outside the course subset, such as pointers (int *p), structs, switch or the ternary operator.
fix: Rewrite with supported features: use arrays and plain variables instead of pointers, if/else instead of switch.

## fix: SEM-UNDECLARED-VAR
code: SEM-UNDECLARED-VAR
phase: semantic
rule_ref: sem.declare_before_use
mistake: Using a variable that was never declared, or declared later or in another block.
fix: Declare it with a type before its first use, in a scope that encloses the use (for example int y = 0;).

## fix: SEM-UNDECLARED-FUNC
code: SEM-UNDECLARED-FUNC
phase: semantic
rule_ref: sem.declare_before_use
mistake: Calling a function that is defined further down the file or not at all.
fix: Move the function above its first call, or add a prototype such as int foo(int a); before it.

## fix: SEM-REDECLARED
code: SEM-REDECLARED
phase: semantic
rule_ref: sem.unique_in_scope
mistake: Declaring the same name twice in one block, often by copy and paste.
fix: Remove the second declaration, or give the variable a different name; assign to it instead of redeclaring.

## fix: SEM-CONFLICTING-TYPES
code: SEM-CONFLICTING-TYPES
phase: semantic
rule_ref: sem.function_declarations
mistake: A prototype and the definition of a function disagree about the return type or parameter types.
fix: Make the prototype and the definition use the same return type and parameter types.

## fix: SEM-TYPE-MISMATCH
code: SEM-TYPE-MISMATCH
phase: semantic
rule_ref: sem.type_compat
mistake: Storing or passing a value of the wrong type, such as a string in an int, as in int x = "hi";.
fix: Use a value of the declared type, or declare the variable with the type the value has.

## fix: SEM-VOID-VALUE
code: SEM-VOID-VALUE
phase: semantic
rule_ref: sem.no_void_values
mistake: Using the result of a void function as a value, as in int x = log();.
fix: Call the void function as a statement on its own, or change the function to return a value.

## fix: SEM-NOT-CALLABLE
code: SEM-NOT-CALLABLE
phase: semantic
rule_ref: sem.call_signature
mistake: Writing parentheses after a name that is a variable, as in x(1).
fix: Call only functions; remove the parentheses, or use the name of the function you meant.

## fix: SEM-ARG-COUNT
code: SEM-ARG-COUNT
phase: semantic
rule_ref: sem.call_signature
mistake: Calling a function with too few or too many arguments.
fix: Pass exactly one argument for each parameter in the function's declaration.

## fix: SEM-ARG-TYPE
code: SEM-ARG-TYPE
phase: semantic
rule_ref: sem.call_signature
mistake: Passing an argument whose type does not fit the parameter, such as a string for an int.
fix: Pass a value of the parameter's type, or change the parameter's type.

## fix: SEM-RETURN-TYPE
code: SEM-RETURN-TYPE
phase: semantic
rule_ref: sem.return_type
mistake: Returning a value from a void function, or returning the wrong type, or return; in an int function.
fix: Return an expression of the function's return type, or return nothing in a void function.

## fix: SEM-NOT-ARRAY
code: SEM-NOT-ARRAY
phase: semantic
rule_ref: sem.array_access
mistake: Indexing a variable that was not declared as an array, as in x[0] with int x;.
fix: Declare the name as an array (int x[10];) or remove the [ ].

## fix: SEM-INDEX-NOT-INT
code: SEM-INDEX-NOT-INT
phase: semantic
rule_ref: sem.array_access
mistake: Using a float or other non-integer value as an array index, as in a[1.5].
fix: Use an int expression for the index.

## fix: SEM-BAD-ARRAY-SIZE
code: SEM-BAD-ARRAY-SIZE
phase: semantic
rule_ref: sem.array_access
mistake: Giving an array a size that is a variable or zero, as in int a[n];.
fix: Use a literal integer greater than 0, for example int a[10];.

## fix: SEM-BREAK-OUTSIDE-LOOP
code: SEM-BREAK-OUTSIDE-LOOP
phase: semantic
rule_ref: sem.loop_control
mistake: Writing break or continue outside any while or for loop.
fix: Move it inside a loop, or use return or an if to leave the function early.

## fix: SEM-NONCONST-GLOBAL-INIT
code: SEM-NONCONST-GLOBAL-INIT
phase: semantic
rule_ref: sem.global_init
mistake: Initialising a global variable with an expression that uses another variable, as in int y = x + 1;.
fix: Initialise the global with a literal, and compute the value inside main.

## fix: SEM-PRINTF-FORMAT
code: SEM-PRINTF-FORMAT
phase: semantic
rule_ref: sem.builtins
mistake: Passing a variable as the first argument of printf, as in printf(x);.
fix: Use a string literal as the first argument: printf("%d", x);.

## fix: SEM-MISSING-MAIN
code: SEM-MISSING-MAIN
phase: semantic
rule_ref: sem.entry_point
mistake: The file defines no int main() function.
fix: Add int main() { ... return 0; } to the program.

## fix: WRN-UNUSED-VAR
code: WRN-UNUSED-VAR
phase: semantic
rule_ref: sem.unused_declaration
mistake: Declaring a variable and never reading it.
fix: Use the variable, or delete the declaration.

## fix: WRN-UNREACHABLE-CODE
code: WRN-UNREACHABLE-CODE
phase: semantic
rule_ref: sem.unreachable
mistake: Writing a statement after return, break or continue, where it can never run.
fix: Delete the statement, or move it before the return, break or continue.

## fix: WRN-IMPLICIT-NARROWING
code: WRN-IMPLICIT-NARROWING
phase: semantic
rule_ref: sem.type_compat
mistake: Storing a float or double into an int, as in int n = 2.5;, which drops the fraction.
fix: Declare the variable as float or double, or accept the loss on purpose by using a whole-number value.

## fix: WRN-MISSING-RETURN
code: WRN-MISSING-RETURN
phase: semantic
rule_ref: sem.return_paths
mistake: A non-void function has a path, such as a missing else, that ends without a return.
fix: Add a return on every path, for example a final return at the end of the function.

## fix: WRN-ASSIGN-IN-CONDITION
code: WRN-ASSIGN-IN-CONDITION
phase: semantic
rule_ref: sem.conditions
mistake: Writing = in an if or while condition when == was meant, as in if (x = 5).
fix: Use == to compare. Keep = only if you really want to assign.
