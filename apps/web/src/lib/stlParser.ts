// Parser STL próprio -- sem dependência externa de loader (Incremento 2.1, item 6; estendido no
// Incremento 2.2 -- item "consolidar visualizador 3D" -- para reconhecer STL ASCII, que o
// parser original não suportava e que um STL ASCII válido faria falhar de forma confusa
// (leitura de bytes de texto como se fossem floats binários).
export interface ParsedStl {
  positions: Float32Array; // 9 floats por triângulo (3 vértices x xyz), não indexado
  normals: Float32Array;
  triangleCount: number;
  format: "binary" | "ascii";
}

const BINARY_HEADER_SIZE = 84;
const BYTES_PER_TRIANGLE_BINARY = 50; // 12 (normal) + 3*12 (vértices) + 2 (attribute byte count)

/** Detecta se o buffer é um STL ASCII válido pela assinatura ("solid" no início) E pela
 * ausência de uma contagem binária de triângulos consistente -- um nome de sólido binário
 * poderia começar com bytes que decodificam como "solid" por coincidência, então a checagem
 * de tamanho esperado do binário é usada como desempate (mesmo princípio já usado em
 * parseBinaryStl: nunca assumir, sempre validar o tamanho contra o que o cabeçalho declara). */
export function detectStlFormat(buffer: ArrayBuffer): "binary" | "ascii" {
  if (buffer.byteLength < 5) return "binary"; // deixa parseBinaryStl rejeitar com mensagem clara
  const head = new Uint8Array(buffer, 0, Math.min(5, buffer.byteLength));
  const asText = String.fromCharCode(...head);
  if (asText.toLowerCase() !== "solid") return "binary";

  if (buffer.byteLength >= BINARY_HEADER_SIZE) {
    const view = new DataView(buffer);
    const declaredTriangles = view.getUint32(80, true);
    const expectedBinarySize = BINARY_HEADER_SIZE + declaredTriangles * BYTES_PER_TRIANGLE_BINARY;
    if (expectedBinarySize === buffer.byteLength) {
      // Tamanho bate exatamente com um STL binário válido -- coincidência de nome que começa
      // com "solid", tratar como binário (mais provável estar correto do que um ASCII que por
      // acaso também bate byte a byte).
      return "binary";
    }
  }
  return "ascii";
}

export function parseBinaryStl(buffer: ArrayBuffer): ParsedStl {
  const view = new DataView(buffer);
  if (buffer.byteLength < BINARY_HEADER_SIZE) {
    throw new Error("Arquivo STL binário inválido: menor que o cabeçalho mínimo (84 bytes).");
  }
  const triangleCount = view.getUint32(80, true);
  const expectedSize = BINARY_HEADER_SIZE + triangleCount * BYTES_PER_TRIANGLE_BINARY;
  if (buffer.byteLength < expectedSize) {
    throw new Error(
      `Arquivo STL binário truncado: esperado ${expectedSize} bytes para ${triangleCount} triângulos, recebido ${buffer.byteLength}.`,
    );
  }

  const positions = new Float32Array(triangleCount * 9);
  const normals = new Float32Array(triangleCount * 9);

  let offset = BINARY_HEADER_SIZE;
  for (let i = 0; i < triangleCount; i++) {
    const nx = view.getFloat32(offset, true);
    const ny = view.getFloat32(offset + 4, true);
    const nz = view.getFloat32(offset + 8, true);
    offset += 12;

    for (let v = 0; v < 3; v++) {
      const px = view.getFloat32(offset, true);
      const py = view.getFloat32(offset + 4, true);
      const pz = view.getFloat32(offset + 8, true);
      offset += 12;

      const base = i * 9 + v * 3;
      positions[base] = px;
      positions[base + 1] = py;
      positions[base + 2] = pz;
      normals[base] = nx;
      normals[base + 1] = ny;
      normals[base + 2] = nz;
    }
    offset += 2; // attribute byte count
  }

  return { positions, normals, triangleCount, format: "binary" };
}

const ASCII_FACET_RE =
  /facet\s+normal\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)[\s\S]*?outer\s+loop([\s\S]*?)endloop/gi;
const ASCII_VERTEX_RE = /vertex\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)/gi;

export function parseAsciiStl(buffer: ArrayBuffer): ParsedStl {
  const text = new TextDecoder("utf-8").decode(buffer);
  if (!/^\s*solid/i.test(text)) {
    throw new Error("Arquivo STL ASCII inválido: não começa com 'solid'.");
  }

  const positions: number[] = [];
  const normals: number[] = [];
  let triangleCount = 0;

  let facetMatch: RegExpExecArray | null;
  ASCII_FACET_RE.lastIndex = 0;
  while ((facetMatch = ASCII_FACET_RE.exec(text)) !== null) {
    const nx = Number.parseFloat(facetMatch[1]);
    const ny = Number.parseFloat(facetMatch[2]);
    const nz = Number.parseFloat(facetMatch[3]);
    const loopBody = facetMatch[4];

    const vertices: number[][] = [];
    let vertexMatch: RegExpExecArray | null;
    ASCII_VERTEX_RE.lastIndex = 0;
    while ((vertexMatch = ASCII_VERTEX_RE.exec(loopBody)) !== null) {
      vertices.push([
        Number.parseFloat(vertexMatch[1]),
        Number.parseFloat(vertexMatch[2]),
        Number.parseFloat(vertexMatch[3]),
      ]);
    }
    if (vertices.length !== 3) {
      throw new Error(
        `Arquivo STL ASCII inválido: facet com ${vertices.length} vértice(s) em vez de 3 (triângulo malformado).`,
      );
    }
    for (const [px, py, pz] of vertices) {
      positions.push(px, py, pz);
      normals.push(nx, ny, nz);
    }
    triangleCount += 1;
  }

  if (triangleCount === 0) {
    throw new Error("Arquivo STL ASCII inválido: nenhum facet encontrado (arquivo vazio ou malformado).");
  }

  return {
    positions: Float32Array.from(positions),
    normals: Float32Array.from(normals),
    triangleCount,
    format: "ascii",
  };
}

/** Ponto de entrada único: detecta o formato e delega ao parser correto. Nunca tenta "adivinhar"
 * silenciosamente -- se nenhum dos dois parsers reconhecer o conteúdo, a exceção original (com
 * mensagem específica de qual validação falhou) propaga para o chamador, que deve mostrar um
 * erro sanitizado e NUNCA renderizar uma geometria substituta. */
export function parseStl(buffer: ArrayBuffer): ParsedStl {
  const format = detectStlFormat(buffer);
  return format === "ascii" ? parseAsciiStl(buffer) : parseBinaryStl(buffer);
}
