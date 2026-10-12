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
