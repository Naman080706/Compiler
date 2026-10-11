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
