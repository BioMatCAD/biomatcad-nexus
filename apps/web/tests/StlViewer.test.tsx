import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StlViewer } from "../src/components/viewer/StlViewer";

describe("StlViewer (smoke test)", () => {
  it("mostra o estado vazio quando não há stlUrl (sem depender de WebGL/jsdom)", () => {
    render(<StlViewer stlUrl={null} />);
    expect(screen.getByText(/nenhum artefato disponível/i)).toBeInTheDocument();
  });
});
