// Incremento 2.1.1 (item 9): garante que a cópia local do schema (src/schemas/, usada pela
// validação offline do modo demo) nunca diverge silenciosamente do arquivo canônico
// (schemas/biomatcem/geometry-recipe-v1.schema.json, raiz do monorepo) -- ver
// src/schemas/README.md.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("cópia local do schema BioMatCEM permanece sincronizada com o arquivo canônico", () => {
  it("é byte-a-byte idêntica (após parse JSON) ao arquivo canônico do monorepo", () => {
    const localPath = path.resolve(__dirname, "../src/schemas/geometry-recipe-v1.schema.json");
    const canonicalPath = path.resolve(__dirname, "../../../schemas/biomatcem/geometry-recipe-v1.schema.json");

    const local = JSON.parse(readFileSync(localPath, "utf-8"));
    const canonical = JSON.parse(readFileSync(canonicalPath, "utf-8"));

    expect(local).toEqual(canonical);
  });
});
