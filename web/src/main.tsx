import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./monaco-setup";
import App from "./App";
import "./App.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
