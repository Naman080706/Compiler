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
mistake: Using a preprocessor directive outside the supported ones: #ifdef/#if/#pragma/#undef, a function-like macro such as #define SQ(x), or a header other than stdio.h, stdlib.h, string.h, math.h, ctype.h and stdbool.h.
fix: Keep only #include of the supported headers and object-like '#define NAME value'; replace a function-like macro with a real function and drop conditional compilation.

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
mistake: Using a C feature outside the course subset: goto and labels, function pointers, variadic functions (...), bit-fields, designated initialisers, or register/auto/volatile.
fix: Rewrite with supported features: use break/return or a flag instead of goto, a plain if/else or switch instead of a function pointer, and ordinary members instead of bit-fields.

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

## fix: SEM-DEREF-NON-POINTER
code: SEM-DEREF-NON-POINTER
phase: semantic
rule_ref: sem.pointers
mistake: Using * on a value that is not a pointer, for example *count where count is an int.
fix: Remove the *, or declare the variable as a pointer (int *count) and give it an address with &.

## fix: SEM-ADDR-OF-NON-LVALUE
code: SEM-ADDR-OF-NON-LVALUE
phase: semantic
rule_ref: sem.pointers
mistake: Taking the address of a computed value such as &(a + b) or &5.
fix: Store the value in a variable first and take the address of that variable (&sum), or pass the value itself.

## fix: SEM-NO-SUCH-MEMBER
code: SEM-NO-SUCH-MEMBER
phase: semantic
rule_ref: sem.members
mistake: Misspelling a struct member name, or using a member the struct does not have.
fix: Compare with the struct definition and use an existing member name, or add the member to the struct.

## fix: SEM-MEMBER-ON-NON-STRUCT
code: SEM-MEMBER-ON-NON-STRUCT
phase: semantic
rule_ref: sem.members
mistake: Using . on something that is not a struct or union, such as an int or a pointer.
fix: Use . only on a struct value; for a pointer to a struct use ->. Check that the variable has the type you expect.

## fix: SEM-ARROW-ON-NON-POINTER
code: SEM-ARROW-ON-NON-POINTER
phase: semantic
rule_ref: sem.members
mistake: Using -> on a struct value instead of a pointer to a struct.
fix: Use . when you have the struct itself (b.width) and -> only when you have a pointer (p->width).

## fix: SEM-INCOMPLETE-TYPE
code: SEM-INCOMPLETE-TYPE
phase: semantic
rule_ref: sem.members
mistake: Declaring a variable of a struct that was only declared (struct Node;) and never defined.
fix: Define the struct with its members before declaring variables of it, or use a pointer to it instead.

## fix: SEM-ASSIGN-TO-CONST
code: SEM-ASSIGN-TO-CONST
phase: semantic
rule_ref: sem.const_correctness
mistake: Assigning to a variable declared const, or through a pointer to const.
fix: Remove const from the declaration if the value must change, or stop assigning to it.

## fix: SEM-DUPLICATE-CASE
code: SEM-DUPLICATE-CASE
phase: semantic
rule_ref: sem.switch_stmt
mistake: Writing the same case value twice in one switch (often a copy and paste slip).
fix: Change one label to the intended value or merge the two cases; each value may appear once per switch.

## fix: SEM-CASE-NOT-CONSTANT
code: SEM-CASE-NOT-CONSTANT
phase: semantic
rule_ref: sem.switch_stmt
mistake: Using a variable as a case label.
fix: Use a literal, a character, an enum constant or a #define value; use if / else if for runtime values.

## fix: SEM-SWITCH-NON-INT
code: SEM-SWITCH-NON-INT
phase: semantic
rule_ref: sem.switch_stmt
mistake: Switching on a double, float or pointer.
fix: Switch on an int or char value (for example convert with a cast) or use if / else if.

## fix: SEM-CASE-OUTSIDE-SWITCH
code: SEM-CASE-OUTSIDE-SWITCH
phase: semantic
rule_ref: sem.switch_stmt
mistake: Writing case or default outside a switch body, often after a misplaced brace.
fix: Move the label inside the switch braces, or check that the braces around the switch are balanced.

## fix: WRN-INCOMPATIBLE-POINTER
code: WRN-INCOMPATIBLE-POINTER
phase: semantic
rule_ref: sem.pointers
mistake: Pointing an int pointer at a double (or another different type).
fix: Declare the pointer with the same base type as the variable (double *p = &price) or cast deliberately.

## fix: GCC-ERROR
code: GCC-ERROR
phase: semantic
rule_ref: sem.gcc_fallback
mistake: The program uses a feature outside the course subset, so gcc analysed it and reported an error.
fix: Read gcc's message; it names the line and what to change. The usual causes are the same as the course errors: missing semicolon, undeclared name, wrong type.

## fix: GCC-WARNING
code: GCC-WARNING
phase: semantic
rule_ref: sem.gcc_fallback
mistake: gcc reports a warning for code that is legal but suspicious (unused variable, format mismatch).
fix: Fix the cause gcc names; warnings do not stop the program from compiling but often point at real bugs.

## fix: GCC-NOTE
code: GCC-NOTE
phase: semantic
rule_ref: sem.gcc_fallback
mistake: A note gives extra detail about the gcc error or warning just before it (for example where the earlier declaration is).
fix: Use the note's location to understand the main message; fix the main diagnostic.
