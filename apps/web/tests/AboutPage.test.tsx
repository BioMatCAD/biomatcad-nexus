import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AboutPage } from "../src/pages/AboutPage";

describe("AboutPage", () => {
  it("renderiza a marca, o título e o link de volta", () => {
    render(
      <BrowserRouter>
        <AboutPage />
      </BrowserRouter>
    );
    expect(screen.getByAltText("BioMatCAD Nexus")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /sobre o biomatcad nexus/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /voltar à página inicial/i })).toBeInTheDocument();
  });

  it("menciona explicitamente que não há dados de pacientes nem validação clínica real", () => {
    render(
      <BrowserRouter>
        <AboutPage />
      </BrowserRouter>
    );
    expect(screen.getByText(/não processa dados de pacientes/i)).toBeInTheDocument();
  });
});
