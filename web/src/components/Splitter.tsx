// Draggable divider between the editor and the error panel. The editor's share of the width is
// kept in localStorage so it survives reloads; arrow keys move it in 2% steps.
import { useCallback, useState, type KeyboardEvent, type PointerEvent } from "react";

const SPLIT_KEY = "cea.split";
export const SPLIT_MIN = 25;
export const SPLIT_MAX = 80;
const SPLIT_DEFAULT = 60;

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
