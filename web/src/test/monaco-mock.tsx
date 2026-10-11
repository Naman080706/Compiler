// A stand-in for @monaco-editor/react: Monaco cannot run in jsdom. Editor is a
// textarea that calls onMount with a fake editor and a fake monaco whose
// setModelMarkers is the spy below; DiffEditor renders the patched source.
import { useEffect } from "react";
import { vi } from "vitest";

export const monacoMock = {
  setModelMarkers: vi.fn(),
  model: { id: "model" },
};

interface EditorProps {
  value?: string;
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: unknown, monaco: unknown) => void;
}

export function Editor({ value, onChange, onMount }: EditorProps) {
  useEffect(() => {
    onMount?.({ getModel: () => monacoMock.model }, { editor: { setModelMarkers: monacoMock.setModelMarkers } });
  }, []);
  return <textarea data-testid="editor" value={value} onChange={(e) => onChange?.(e.target.value)} />;
}

export function DiffEditor({ original, modified }: { original?: string; modified?: string }) {
  return (
    <pre data-testid="diff-editor" data-original={original}>
      {modified}
    </pre>
  );
}

export const loader = { config: vi.fn() };
export default Editor;
