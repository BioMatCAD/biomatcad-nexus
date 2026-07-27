import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./theme/tokens.css";

// Base path dinâmico: no build de demo (GitHub Pages) o Vite injeta BASE_URL a partir de
// `base` em vite.config.ts (Prompt Mestre §7.1: "funcionamento correto sob /<repositorio>/").
const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
