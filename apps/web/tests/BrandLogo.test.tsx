import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandLogo } from "../src/components/brand/BrandLogo";

describe("BrandLogo", () => {
  it("variante horizontal usa alt='BioMatCAD Nexus' e caminho sob o base URL", () => {
    render(<BrandLogo variant="horizontal" />);
    const img = screen.getByAltText("BioMatCAD Nexus") as HTMLImageElement;
    expect(img.getAttribute("src")).toMatch(/brand\/biomatcad-nexus-logo-horizontal-web-960\.png$/);
  });

  it("variante symbol usa alt descritivo do símbolo isolado", () => {
    render(<BrandLogo variant="symbol" />);
    const img = screen.getByAltText("Símbolo BioMatCAD Nexus") as HTMLImageElement;
    expect(img.getAttribute("src")).toMatch(/brand\/biomatcad-nexus-symbol-transparent\.png$/);
  });

  it("nunca incorpora a imagem como Base64 (sempre um caminho de arquivo real)", () => {
    render(<BrandLogo variant="horizontal" />);
    const img = screen.getByAltText("BioMatCAD Nexus") as HTMLImageElement;
    expect(img.getAttribute("src")).not.toMatch(/^data:/);
  });
});
