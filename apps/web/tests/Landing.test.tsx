import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { LandingPage } from "../src/pages/LandingPage";

describe("LandingPage", () => {
  it("renderiza o título e o link de entrar", () => {
    render(
      <BrowserRouter>
        <LandingPage />
      </BrowserRouter>
    );
    expect(screen.getByRole("heading", { name: /biomatcad nexus/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /entrar/i })).toBeInTheDocument();
  });
});
