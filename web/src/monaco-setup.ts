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
    { token: "comment", foreground: "73787C", fontStyle: "italic" },
    { token: "keyword", foreground: "C9AD93" },
    { token: "string", foreground: "879A77" },
    { token: "number", foreground: "D7E5F0" },
  ],
  colors: {
    "editor.background": "#222527",
    "editor.foreground": "#D7E5F0",
    "editorLineNumber.foreground": "#73787C",
    "editorLineNumber.activeForeground": "#C5C6C7",
    "editor.lineHighlightBackground": "#2B2E30",
    "editor.selectionBackground": "#554940",
    "editorCursor.foreground": "#C9AD93",
    "editorGutter.background": "#222527",
    "editorBracketMatch.border": "#C9AD93",
    "editorBracketHighlight.foreground1": "#C5C6C7",
    "editorBracketHighlight.foreground2": "#C5C6C7",
    "editorBracketHighlight.foreground3": "#C5C6C7",
    "editorBracketHighlight.foreground4": "#C5C6C7",
    "editorBracketHighlight.foreground5": "#C5C6C7",
    "editorBracketHighlight.foreground6": "#C5C6C7",
  },
});
