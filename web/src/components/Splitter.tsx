// Draggable divider between the editor and the error panel. The editor's share of the width is
// kept in localStorage so it survives reloads; arrow keys move it in 2% steps.
import { useCallback, useState, type KeyboardEvent, type PointerEvent } from "react";

const SPLIT_KEY = "cea.split";
export const SPLIT_MIN = 25;
export const SPLIT_MAX = 82;
const SPLIT_DEFAULT = 68;        // editor gets the larger share by default; the error panel is narrower

const clamp = (v: number) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, v));

function loadSplit(): number {
  try {
    const v = Number(window.localStorage.getItem(SPLIT_KEY));
    return Number.isFinite(v) && v > 0 ? clamp(v) : SPLIT_DEFAULT;
  } catch {
    return SPLIT_DEFAULT;
  }
}

function saveSplit(v: number) {
  try {
    window.localStorage.setItem(SPLIT_KEY, String(v));
  } catch {
    // storage blocked: the split still works for this page load
  }
}

/** The editor's width in percent, and a setter that clamps and persists it. */
export function useSplit(): [number, (v: number) => void] {
  const [split, setSplitState] = useState(loadSplit);
  const setSplit = useCallback((v: number) => {
    const c = clamp(Math.round(v * 10) / 10);
    setSplitState(c);
    saveSplit(c);
  }, []);
  return [split, setSplit];
}

interface Props {
  split: number;
  onChange: (v: number) => void;
}

export default function Splitter({ split, onChange }: Props) {
  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    const container = e.currentTarget.parentElement;
    if (!container) return;
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const move = (ev: globalThis.PointerEvent) => onChange(((ev.clientX - rect.left) / rect.width) * 100);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("resizing");
    };
    document.body.classList.add("resizing");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowLeft") onChange(split - 2);
    else if (e.key === "ArrowRight") onChange(split + 2);
    else return;
    e.preventDefault();
  }

  return (
    <div
      className="splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize editor and error panel"
      aria-valuemin={SPLIT_MIN}
      aria-valuemax={SPLIT_MAX}
      aria-valuenow={Math.round(split)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onDoubleClick={() => onChange(SPLIT_DEFAULT)}
    />
  );
}

// ---------------------------------------------------------------------------
// Vertical splitter: the terminal output panel's height, in pixels, dragged up
// or down between the editor and the terminal. Height is kept in localStorage.
const TERM_KEY = "cea.terminal";
export const TERM_MIN = 72;
export const TERM_DEFAULT = 176;
// Leave at least this much room for the editor above the terminal.
const EDITOR_MIN = 120;

function loadTermHeight(): number {
  try {
    const v = Number(window.localStorage.getItem(TERM_KEY));
    return Number.isFinite(v) && v >= TERM_MIN ? v : TERM_DEFAULT;
  } catch {
    return TERM_DEFAULT;
  }
}

/** The terminal's height in px, and a setter that enforces the lower bound and persists it. */
export function useTerminalHeight(): [number, (v: number) => void] {
  const [height, setHeightState] = useState(loadTermHeight);
  const setHeight = useCallback((v: number) => {
    const c = Math.max(TERM_MIN, Math.round(v));
    setHeightState(c);
    try {
      window.localStorage.setItem(TERM_KEY, String(c));
    } catch {
      // storage blocked: the height still works for this page load
    }
  }, []);
  return [height, setHeight];
}

interface VProps {
  height: number;
  onChange: (v: number) => void;
}

/** Row divider between the editor and the terminal; drag or arrow-key to resize. */
export function VSplitter({ height, onChange }: VProps) {
  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    const container = e.currentTarget.parentElement;
    if (!container) return;
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const max = rect.height - EDITOR_MIN;
    const move = (ev: globalThis.PointerEvent) =>
      onChange(Math.min(max, rect.bottom - ev.clientY));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("resizing-v");
    };
    document.body.classList.add("resizing-v");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowUp") onChange(height + 24);
    else if (e.key === "ArrowDown") onChange(height - 24);
    else return;
    e.preventDefault();
  }

  return (
    <div
      className="vsplitter"
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize the output terminal"
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onDoubleClick={() => onChange(TERM_DEFAULT)}
    />
  );
}
