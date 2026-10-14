// Use the locally installed monaco-editor package instead of the default CDN
// download of @monaco-editor/react, so the demo works offline. Only the editor
// core and C syntax colouring are bundled. Imported only by main.tsx; tests
// mock @monaco-editor/react and never load Monaco.
import * as monaco from "monaco-editor/editor/editor.api";
import "monaco-editor/languages/definitions/cpp/register";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import { loader } from "@monaco-editor/react";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

// Deep-charcoal editor theme matching App.css (palette: black, charcoal, gray, pale blue, beige, taupe, soft green).
monaco.editor.defineTheme("cea-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "comment", foreground: "6E7A86", fontStyle: "italic" },
    { token: "keyword", foreground: "E0B88A" },
    { token: "string", foreground: "8FBF8A" },
    { token: "number", foreground: "8CC4E8" },
  ],
  colors: {
    "editor.background": "#22262B",
    "editor.foreground": "#E6EDF3",
    "editorLineNumber.foreground": "#5A6570",
    "editorLineNumber.activeForeground": "#9AA7B4",
    "editor.lineHighlightBackground": "#2A2F35",
    "editor.selectionBackground": "#3A4552",
    "editorCursor.foreground": "#E0B88A",
    "editorGutter.background": "#22262B",
    "editorBracketMatch.border": "#E0B88A",
    "editorBracketHighlight.foreground1": "#9AA7B4",
    "editorBracketHighlight.foreground2": "#9AA7B4",
    "editorBracketHighlight.foreground3": "#9AA7B4",
    "editorBracketHighlight.foreground4": "#9AA7B4",
    "editorBracketHighlight.foreground5": "#9AA7B4",
    "editorBracketHighlight.foreground6": "#9AA7B4",
  },
});

// Autocomplete for C: keywords, types, common library functions and a few snippets.
const C_KEYWORDS = [
  "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum", "extern",
  "float", "for", "goto", "if", "int", "long", "register", "return", "short", "signed", "sizeof", "static",
  "struct", "switch", "typedef", "union", "unsigned", "void", "volatile", "while", "NULL", "true", "false", "bool",
];
const C_FUNCTIONS: [string, string][] = [
  ["printf", "printf(\"${1:%d}\n\", ${2});"], ["scanf", "scanf(\"${1:%d}\", &${2:x});"],
  ["puts", "puts(\"${1}\");"], ["getchar", "getchar()"], ["putchar", "putchar(${1})"],
  ["malloc", "malloc(${1:n} * sizeof(${2:int}))"], ["calloc", "calloc(${1:n}, sizeof(${2:int}))"], ["free", "free(${1:ptr});"],
  ["strlen", "strlen(${1:s})"], ["strcpy", "strcpy(${1:dest}, ${2:src});"], ["strcmp", "strcmp(${1:a}, ${2:b})"],
  ["strcat", "strcat(${1:dest}, ${2:src});"], ["sqrt", "sqrt(${1:x})"], ["pow", "pow(${1:x}, ${2:y})"],
  ["abs", "abs(${1:x})"], ["toupper", "toupper(${1:c})"], ["tolower", "tolower(${1:c})"], ["exit", "exit(${1:0});"],
];
const C_SNIPPETS: [string, string, string][] = [
  ["main", "int main(void) {\n\t${1}\n\treturn 0;\n}", "main function"],
  ["for", "for (int ${1:i} = 0; ${1:i} < ${2:n}; ${1:i}++) {\n\t${3}\n}", "for loop"],
  ["while", "while (${1:condition}) {\n\t${2}\n}", "while loop"],
  ["do", "do {\n\t${1}\n} while (${2:condition});", "do-while loop"],
  ["if", "if (${1:condition}) {\n\t${2}\n}", "if statement"],
  ["ifelse", "if (${1:condition}) {\n\t${2}\n} else {\n\t${3}\n}", "if / else"],
  ["switch", "switch (${1:x}) {\ncase ${2:1}:\n\t${3}\n\tbreak;\ndefault:\n\tbreak;\n}", "switch statement"],
  ["struct", "struct ${1:Name} {\n\t${2:int field;}\n};", "struct definition"],
  ["include", "#include <${1:stdio.h}>", "include a header"],
];

monaco.languages.registerCompletionItemProvider("cpp", {
  provideCompletionItems(model, position) {
    const word = model.getWordUntilPosition(position);
    const range = {
      startLineNumber: position.lineNumber, endLineNumber: position.lineNumber,
      startColumn: word.startColumn, endColumn: word.endColumn,
    };
    const { CompletionItemKind: K, CompletionItemInsertTextRule: R } = monaco.languages;
    return {
      suggestions: [
        ...C_KEYWORDS.map((k) => ({ label: k, kind: K.Keyword, insertText: k, range })),
        ...C_FUNCTIONS.map(([label, body]) => ({
          label, kind: K.Function, insertText: body, insertTextRules: R.InsertAsSnippet, range, detail: "C library",
        })),
        ...C_SNIPPETS.map(([label, body, detail]) => ({
          label, kind: K.Snippet, insertText: body, insertTextRules: R.InsertAsSnippet, range, detail,
        })),
      ],
    };
  },
});
