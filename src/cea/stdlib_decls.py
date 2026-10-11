"""Builtin declarations of the supported standard headers (language-spec.md, sem.builtins).

A header's names become visible when its ``#include`` appears before the use.
Types are written as C text (``const char*``, ``size_t``) and turned into
semantic types by ``cea.semantic``; this module is data only and imports nothing
from the compiler.
"""
from __future__ import annotations

import re

# One declaration per line: "<return type> <name>(<parameter types>)"; "..." marks a variadic function.
FUNCTIONS: dict[str, str] = {
    "stdio.h": """
        int printf(const char*, ...)
        int scanf(const char*, ...)
        int sprintf(char*, const char*, ...)
        int snprintf(char*, size_t, const char*, ...)
        int sscanf(const char*, const char*, ...)
        int fprintf(FILE*, const char*, ...)
        int fscanf(FILE*, const char*, ...)
        int puts(const char*)
        int putchar(int)
        int getchar(void)
        int fputs(const char*, FILE*)
        int fputc(int, FILE*)
        int fgetc(FILE*)
        char* fgets(char*, int, FILE*)
        FILE* fopen(const char*, const char*)
        int fclose(FILE*)
        int fflush(FILE*)
        int feof(FILE*)
        void perror(const char*)
    """,
    "stdlib.h": """
        void* malloc(size_t)
        void* calloc(size_t, size_t)
        void* realloc(void*, size_t)
        void free(void*)
        void exit(int)
        int abs(int)
        long labs(long)
        int atoi(const char*)
        long atol(const char*)
        double atof(const char*)
        int rand(void)
        void srand(unsigned int)
    """,
    "string.h": """
        size_t strlen(const char*)
        char* strcpy(char*, const char*)
        char* strncpy(char*, const char*, size_t)
        char* strcat(char*, const char*)
        char* strncat(char*, const char*, size_t)
        int strcmp(const char*, const char*)
        int strncmp(const char*, const char*, size_t)
        char* strchr(const char*, int)
        char* strrchr(const char*, int)
        char* strstr(const char*, const char*)
        void* memset(void*, int, size_t)
        void* memcpy(void*, const void*, size_t)
        void* memmove(void*, const void*, size_t)
        int memcmp(const void*, const void*, size_t)
    """,
    "math.h": "\n".join(f"double {n}(double)" for n in (
        "sqrt sin cos tan asin acos atan exp log log10 fabs floor ceil round trunc sinh cosh tanh cbrt").split()) + """
        double pow(double, double)
        double atan2(double, double)
        double fmod(double, double)
        double hypot(double, double)
        double fmax(double, double)
        double fmin(double, double)
    """,
    "ctype.h": "\n".join(f"int {n}(int)" for n in (
        "isalpha isdigit isalnum isspace isupper islower ispunct isprint isxdigit iscntrl isgraph "
        "toupper tolower").split()),
    "stdbool.h": "",
}

# name -> C type text, per header (object-like names that are not macros of the user)
CONSTANTS: dict[str, dict[str, str]] = {
    "stdio.h": {"EOF": "int", "NULL": "void*", "stdin": "FILE*", "stdout": "FILE*", "stderr": "FILE*"},
    "stdlib.h": {"NULL": "void*", "EXIT_SUCCESS": "int", "EXIT_FAILURE": "int", "RAND_MAX": "int"},
    "string.h": {"NULL": "void*"},
    "stdbool.h": {"true": "int", "false": "int"},
}
# integer value of a constant, where known (for case labels and array sizes)
CONSTANT_VALUES = {"EOF": -1, "EXIT_SUCCESS": 0, "EXIT_FAILURE": 1, "true": 1, "false": 0}

# typedef name -> C type text, per header
TYPEDEFS: dict[str, dict[str, str]] = {
    "stdio.h": {"size_t": "unsigned long", "FILE": "FILE"},
    "stdlib.h": {"size_t": "unsigned long"},
    "string.h": {"size_t": "unsigned long"},
    "stdbool.h": {"bool": "_Bool"},
}

_LINE = re.compile(r"^(.*?)(\w+)\((.*)\)$")


def parse_functions(header: str) -> list[tuple[str, str, list[str], bool]]:
    """[(name, return type text, [parameter type texts], variadic)] of one header."""
    out = []
    for raw in FUNCTIONS.get(header, "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LINE.match(line)
        assert m, line
        ret, name, params = m.group(1).strip(), m.group(2), [p.strip() for p in m.group(3).split(",") if p.strip()]
        variadic = bool(params) and params[-1] == "..."
        params = [p for p in params if p not in ("...", "void")]
        out.append((name, ret, params, variadic))
    return out
