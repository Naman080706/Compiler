// The Monaco source editor with inline error markers (setModelMarkers).
import Editor, { type Monaco, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { toMarkers } from "../clusters";
import type { ErrorRecord } from "../types";

export const MARKER_OWNER = "cea";

type EditorInstance = Parameters<OnMount>[0];
type MarkerList = Parameters<Monaco["editor"]["setModelMarkers"]>[2];

interface Props {
  value: string;
  onChange: (value: string) => void;
  records: ErrorRecord[];
}

export default function CodeEditor({ value, onChange, records }: Props) {
  const mounted = useRef<{ editor: EditorInstance; monaco: Monaco } | null>(null);
  const [ready, setReady] = useState(false);

  const handleMount: OnMount = (editor, monaco) => {
    mounted.current = { editor, monaco };
    setReady(true);
  };

  useEffect(() => {
    const m = mounted.current;
    const model = m?.editor.getModel();
    if (!m || !model) return;
    m.monaco.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(records) as MarkerList);
  }, [records, ready]);

  return (
    <Editor
      height="100%"
      defaultLanguage="c"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={handleMount}
      theme="cea-dark"
      options={{ automaticLayout: true, minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false, bracketPairColorization: { enabled: false } }}
    />
  );
}
