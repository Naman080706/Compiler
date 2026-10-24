// Practice drills (#/practice): tiny buggy C programs, one per common error category.
// The Practice page orders them by the categories the student gets wrong most (from their
// F9 profile), so they drill their own weak spots. A drill is "solved" when it compiles.
export interface Drill {
  category: string; // matches the catalog category names used by the profile
  prompt: string;
  code: string;
}

export const DRILLS: Drill[] = [
  {
    category: "missing-semicolon",
    prompt: "This program is missing a semicolon. Add it so the program compiles.",
    code: '#include <stdio.h>\n\nint main(void) {\n    int total = 0\n    total = total + 5;\n    printf("%d\\n", total);\n    return 0;\n}\n',
  },
  {
    category: "undeclared-identifier",
    prompt: "A variable is used before it is declared. Declare it with the right type.",
    code: '#include <stdio.h>\n\nint main(void) {\n    count = 3;\n    printf("%d\\n", count);\n    return 0;\n}\n',
  },
  {
    category: "type-mismatch",
    prompt: "This function should return an int but returns nothing. Fix the return.",
    code: '#include <stdio.h>\n\nint add(int a, int b) {\n    return;\n}\n\nint main(void) {\n    printf("%d\\n", add(2, 3));\n    return 0;\n}\n',
  },
  {
    category: "unbalanced-braces",
    prompt: "A closing brace is missing. Balance the braces so it compiles.",
    code: '#include <stdio.h>\n\nint main(void) {\n    if (1) {\n        printf("hi\\n");\n    return 0;\n}\n',
  },
];

/** Drills ordered so the student's most-missed categories come first (then the rest, stable). */
export function orderDrills(topCategories: string[]): Drill[] {
  const rank = new Map(topCategories.map((c, i) => [c, i]));
  return [...DRILLS].sort((a, b) => (rank.get(a.category) ?? 99) - (rank.get(b.category) ?? 99));
}
