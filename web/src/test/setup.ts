// Vitest setup: jest-dom matchers, the Monaco mock, and cleanup after each test.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { monacoMock } from "./monaco-mock";

vi.mock("@monaco-editor/react", () => import("./monaco-mock"));

afterEach(() => {
  cleanup();
  monacoMock.setModelMarkers.mockReset();
});
