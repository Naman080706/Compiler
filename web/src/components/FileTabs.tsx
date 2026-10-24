// A tab strip above the editor for working on several programs at once, plus
// "New" (a blank file) and "Open…" (one or more .c files from the user's
// computer, read in the browser with File.text() — nothing is uploaded).
import { useRef, useState, type ChangeEvent } from "react";

export interface TabInfo {
  id: string;
  name: string;
  dirty: boolean; // edited since its last compile (or never compiled)
}

interface Props {
  files: TabInfo[];
  activeId: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onNew: () => void;
  onOpen: (files: FileList) => void;
  onRename: (id: string, name: string) => void;
}

export default function FileTabs({ files, activeId, onSelect, onClose, onNew, onOpen, onRename }: Props) {
  const input = useRef<HTMLInputElement>(null);
  // Double-click a tab name to rename it in place; Enter / blur commits, Escape cancels.
  const [editing, setEditing] = useState<{ id: string; draft: string } | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) onOpen(e.target.files);
    e.target.value = ""; // let the same file be re-opened later
  }

  function startRename(id: string, name: string) {
    onSelect(id);
    setEditing({ id, draft: name });
  }

  function commitRename() {
    if (editing) onRename(editing.id, editing.draft);
    setEditing(null);
  }

  return (
    <div className="filebar" role="tablist" aria-label="Open files">
      <div className="filetabs">
        {files.map((f) => (
          <div
            key={f.id}
            role="tab"
            aria-selected={f.id === activeId}
            tabIndex={f.id === activeId ? 0 : -1}
            className={`filetab${f.id === activeId ? " active" : ""}`}
            title={f.name}
            onClick={() => onSelect(f.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(f.id);
              }
            }}
          >
            {f.dirty && <span className="filetab-dot" aria-hidden="true" />}
            {editing?.id === f.id ? (
              <input
                className="filetab-edit"
                aria-label={`Rename ${f.name}`}
                autoFocus
                value={editing.draft}
                onChange={(e) => setEditing({ id: f.id, draft: e.target.value })}
                onClick={(e) => e.stopPropagation()}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  e.stopPropagation(); // don't let the tab's own key handler see typing
                  if (e.key === "Enter") {
                    e.preventDefault();
                    commitRename();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    setEditing(null);
                  }
                }}
              />
            ) : (
              <span className="filetab-name" onDoubleClick={() => startRename(f.id, f.name)} title="Double-click to rename">
                {f.name}
              </span>
            )}
            <button
              type="button"
              className="filetab-close"
              aria-label={`Close ${f.name}`}
              onClick={(e) => {
                e.stopPropagation();
                onClose(f.id);
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="file-actions">
        <button type="button" className="file-btn" onClick={onNew} title="New blank file">
          + New
        </button>
        <button type="button" className="file-btn" onClick={() => input.current?.click()} title="Open .c files from your computer">
          Open…
        </button>
        <input
          ref={input}
          type="file"
          accept=".c,.h,.cc,.cpp,.txt,text/plain"
          multiple
          hidden
          aria-hidden="true"
          onChange={pick}
        />
      </div>
    </div>
  );
}
