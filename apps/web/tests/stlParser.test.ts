import { describe, expect, it } from "vitest";
import { detectStlFormat, parseAsciiStl, parseBinaryStl, parseStl } from "../src/lib/stlParser";

function buildBinaryStl(triangleCount: number): ArrayBuffer {
  const size = 84 + triangleCount * 50;
  const buffer = new ArrayBuffer(size);
  const view = new DataView(buffer);
  view.setUint32(80, triangleCount, true);
  let offset = 84;
  for (let i = 0; i < triangleCount; i++) {
    view.setFloat32(offset, 0, true); // normal x
    view.setFloat32(offset + 4, 0, true);
    view.setFloat32(offset + 8, 1, true);
    offset += 12;
    for (let v = 0; v < 3; v++) {
      view.setFloat32(offset, i + v, true);
      view.setFloat32(offset + 4, i + v, true);
      view.setFloat32(offset + 8, i + v, true);
      offset += 12;
    }
    offset += 2;
  }
  return buffer;
}

const ASCII_STL = `solid demo
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex 1 0 0
    vertex 1 1 0
    vertex 0 1 0
  endloop
endfacet
endsolid demo
`;

function asciiBuffer(text: string): ArrayBuffer {
  return new TextEncoder().encode(text).buffer;
}

describe("parseBinaryStl", () => {
  it("faz parse de um STL binário válido com 2 triângulos", () => {
    const parsed = parseBinaryStl(buildBinaryStl(2));
    expect(parsed.triangleCount).toBe(2);
    expect(parsed.format).toBe("binary");
    expect(parsed.positions).toHaveLength(2 * 9);
  });

  it("rejeita um arquivo menor que o cabeçalho mínimo", () => {
    expect(() => parseBinaryStl(new ArrayBuffer(10))).toThrow(/menor que o cabeçalho mínimo/);
  });

  it("rejeita um arquivo binário truncado (declara mais triângulos do que cabe)", () => {
    const buffer = buildBinaryStl(5);
    const truncated = buffer.slice(0, buffer.byteLength - 10);
    expect(() => parseBinaryStl(truncated)).toThrow(/truncado/);
  });
});

describe("parseAsciiStl", () => {
  it("faz parse de um STL ASCII válido com 2 facets", () => {
    const parsed = parseAsciiStl(asciiBuffer(ASCII_STL));
    expect(parsed.triangleCount).toBe(2);
    expect(parsed.format).toBe("ascii");
    expect(parsed.positions).toHaveLength(2 * 9);
    // primeiro vértice do primeiro facet: (0,0,0)
    expect(parsed.positions[0]).toBe(0);
    expect(parsed.positions[1]).toBe(0);
    expect(parsed.positions[2]).toBe(0);
  });

  it("rejeita um arquivo que não começa com 'solid'", () => {
    expect(() => parseAsciiStl(asciiBuffer("not-an-stl-file\n"))).toThrow(/não começa com 'solid'/);
  });

  it("rejeita um facet malformado com número errado de vértices", () => {
    const malformed = `solid x\nfacet normal 0 0 1\n  outer loop\n    vertex 0 0 0\n    vertex 1 0 0\n  endloop\nendfacet\nendsolid x\n`;
    expect(() => parseAsciiStl(asciiBuffer(malformed))).toThrow(/facet com 2 vértice/);
  });

  it("rejeita um STL ASCII vazio (sem nenhum facet)", () => {
    expect(() => parseAsciiStl(asciiBuffer("solid vazio\nendsolid vazio\n"))).toThrow(/nenhum facet encontrado/);
  });
});

describe("detectStlFormat", () => {
  it("detecta STL binário mesmo quando o buffer é curto", () => {
    expect(detectStlFormat(buildBinaryStl(1))).toBe("binary");
  });

  it("detecta STL ASCII pela assinatura 'solid' quando o tamanho não bate com um binário válido", () => {
    expect(detectStlFormat(asciiBuffer(ASCII_STL))).toBe("ascii");
  });
});

describe("parseStl (ponto de entrada único)", () => {
  it("delega para o parser binário quando o formato é binário", () => {
    expect(parseStl(buildBinaryStl(3)).format).toBe("binary");
  });

  it("delega para o parser ASCII quando o formato é ASCII", () => {
    expect(parseStl(asciiBuffer(ASCII_STL)).format).toBe("ascii");
  });
});
