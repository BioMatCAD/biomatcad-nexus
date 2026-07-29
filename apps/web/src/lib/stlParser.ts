// Parser STL binário próprio -- sem dependência externa de loader (Incremento 2.1, item 6).
export interface ParsedStl {
  positions: Float32Array; // 9 floats por triângulo (3 vértices x xyz), não indexado
  normals: Float32Array;
  triangleCount: number;
}

export function parseBinaryStl(buffer: ArrayBuffer): ParsedStl {
  const view = new DataView(buffer);
  if (buffer.byteLength < 84) {
    throw new Error("Arquivo STL binário inválido: menor que o cabeçalho mínimo (84 bytes).");
  }
  const triangleCount = view.getUint32(80, true);
  const expectedSize = 84 + triangleCount * 50;
  if (buffer.byteLength < expectedSize) {
    throw new Error(
      `Arquivo STL binário truncado: esperado ${expectedSize} bytes para ${triangleCount} triângulos, recebido ${buffer.byteLength}.`,
    );
  }

  const positions = new Float32Array(triangleCount * 9);
  const normals = new Float32Array(triangleCount * 9);

  let offset = 84;
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

  return { positions, normals, triangleCount };
}
