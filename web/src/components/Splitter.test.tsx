import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import Splitter, { SPLIT_MAX, SPLIT_MIN } from "./Splitter";

function Harness({ start }: { start: number }) {
  const [split, setSplit] = useState(start);
  return <Splitter split={split} onChange={(v) => setSplit(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, v)))} />;
}

describe("Splitter", () => {
  it("moves with the arrow keys and exposes its value", () => {
    render(<Harness start={60} />);
    const sep = screen.getByRole("separator", { name: "Resize editor and error panel" });
    expect(sep).toHaveAttribute("aria-valuenow", "60");
    fireEvent.keyDown(sep, { key: "ArrowLeft" });
    expect(sep).toHaveAttribute("aria-valuenow", "58");
    fireEvent.keyDown(sep, { key: "ArrowRight" });
    fireEvent.keyDown(sep, { key: "ArrowRight" });
    expect(sep).toHaveAttribute("aria-valuenow", "62");
  });

  it("resets to the default on double-click", () => {
    render(<Harness start={30} />);
    const sep = screen.getByRole("separator");
    fireEvent.doubleClick(sep);
    expect(sep).toHaveAttribute("aria-valuenow", "60");
  });
});
