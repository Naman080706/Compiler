// The real /api/compile response for SAMPLE_SOURCE (src/sample.ts), captured from the plan-012 backend.
import type { CompileResponse } from "../types";

export const SAMPLE_COMPILE: CompileResponse = {
  ok: false,
  summary: "6 fatal, 1 warning",
  records: [
    {"id": "E-0001", "phase": "syntax", "code": "SYN-MISSING-SEMICOLON", "severity": "fatal", "line": 9, "column": 26, "found": "return", "expected": [";"], "snippet": "    }\n    printf(\"%d\\n\", total)\n    return 0;", "root_id": "E-0001", "rule_ref": "expr_stmt", "language": "c", "caused_by": null, "span_end": {"line": 9, "column": 26}, "message": "Expected ';' after the expression statement but found 'return'"},
    {"id": "E-0002", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 10, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 10}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0003", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 17, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 17}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0004", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 24, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 24}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0005", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 28, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 28}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0006", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 7, "column": 25, "found": "i", "expected": [], "snippet": "    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;\n    }", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 7, "column": 25}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0007", "phase": "semantic", "code": "WRN-UNUSED-VAR", "severity": "warning", "line": 5, "column": 9, "found": "unused", "expected": [], "snippet": "    int total = 0;\n    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {", "root_id": "E-0007", "rule_ref": "sem.unused_declaration", "language": "c", "caused_by": null, "span_end": {"line": 5, "column": 14}, "message": "Variable 'unused' is declared but never used"},
  ],
  clusters: [
    {"root_id": "E-0007", "symptom_ids": []},
    {"root_id": "E-0002", "symptom_ids": ["E-0003", "E-0004", "E-0005", "E-0006"]},
    {"root_id": "E-0001", "symptom_ids": []},
  ],
};
