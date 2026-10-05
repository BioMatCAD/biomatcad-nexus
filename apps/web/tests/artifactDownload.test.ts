import { describe, expect, it, vi } from "vitest";
import {
  ArtifactChecksumMismatchError,
  ArtifactTooLargeError,
  downloadArtifactAsFile,
  fetchArtifactBuffer,
  sanitizeFilename,
  sha256Hex,
} from "../src/lib/artifactDownload";

function bufferFromText(text: string): ArrayBuffer {
  return new TextEncoder().encode(text).buffer;
}

describe("sha256Hex", () => {
  it("calcula um SHA-256 determinístico conhecido", async () => {
    await expect(sha256Hex(bufferFromText("BioMatCAD Nexus"))).resolves.toBe(
      "fdfe0fb700e7f940b1e2c81d6f0c25a3bae447e797649d3fde455ee540440c05",
    );
  });

  it("normaliza o BufferSource para Uint8Array antes de chamar WebCrypto", async () => {
    const digestMock = vi.fn().mockImplementation(async (_algorithm: AlgorithmIdentifier, data: BufferSource) => {
      expect(data).toBeInstanceOf(Uint8Array);
      return new ArrayBuffer(32);
    });
    vi.stubGlobal("crypto", { subtle: { digest: digestMock } });

    try {
      await expect(sha256Hex(bufferFromText("realm-safe"))).resolves.toBe("00".repeat(32));
      expect(digestMock).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("fetchArtifactBuffer", () => {
  it("envia o token via header Authorization, nunca na URL", async () => {
    const buffer = bufferFromText("conteudo-stl-de-teste");
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const headers = init?.headers as Headers;
      expect(headers.get("Authorization")).toBe("Bearer meu-token-secreto");
      expect(url).not.toContain("meu-token-secreto");
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "Content-Length": String(buffer.byteLength) }),
        arrayBuffer: async () => buffer,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchArtifactBuffer("https://api.example/artifacts/1/download", {
      token: "meu-token-secreto",
    });
    expect(result.buffer.byteLength).toBe(buffer.byteLength);
    vi.unstubAllGlobals();
  });

  it("rejeita quando o status HTTP não é OK (ex.: 401 não autorizado)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, headers: new Headers() }),
    );
    await expect(fetchArtifactBuffer("https://api.example/x")).rejects.toThrow(/status 401/);
    vi.unstubAllGlobals();
  });

  it("rejeita ANTES de ler o corpo quando Content-Length declarado excede o limite", async () => {
    const arrayBufferSpy = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "Content-Length": "999999999" }),
        arrayBuffer: arrayBufferSpy,
      }),
    );
    await expect(
      fetchArtifactBuffer("https://api.example/x", { maxBytes: 1000 }),
    ).rejects.toBeInstanceOf(ArtifactTooLargeError);
    expect(arrayBufferSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("rejeita também quando o backend não declara Content-Length mas o corpo real excede o limite", async () => {
    const bigBuffer = new ArrayBuffer(2000);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, headers: new Headers(), arrayBuffer: async () => bigBuffer }),
    );
    await expect(
      fetchArtifactBuffer("https://api.example/x", { maxBytes: 1000 }),
    ).rejects.toBeInstanceOf(ArtifactTooLargeError);
    vi.unstubAllGlobals();
  });

  it("calcula o SHA-256 real dos bytes recebidos e detecta divergência de checksum", async () => {
    const buffer = bufferFromText("bytes-corrompidos-ou-alterados");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, headers: new Headers(), arrayBuffer: async () => buffer }),
    );
    await expect(
      fetchArtifactBuffer("https://api.example/x", { expectedSha256: "0".repeat(64) }),
    ).rejects.toBeInstanceOf(ArtifactChecksumMismatchError);
    vi.unstubAllGlobals();
  });

  it("aceita quando o checksum esperado bate com o calculado de fato", async () => {
    const buffer = bufferFromText("conteudo-integro");
    const expected = await sha256Hex(buffer);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, headers: new Headers(), arrayBuffer: async () => buffer }),
    );
    const result = await fetchArtifactBuffer("https://api.example/x", { expectedSha256: expected });
    expect(result.sha256).toBe(expected);
    vi.unstubAllGlobals();
  });

  it("propaga o AbortSignal para o fetch (cancelamento real)", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      expect(init?.signal).toBe(controller.signal);
      return Promise.reject(new DOMException("Aborted", "AbortError"));
    });
    vi.stubGlobal("fetch", fetchMock);
    controller.abort();
    await expect(
      fetchArtifactBuffer("https://api.example/x", { signal: controller.signal }),
    ).rejects.toThrow();
    vi.unstubAllGlobals();
  });
});

describe("downloadArtifactAsFile", () => {
  it("cria e revoga o ObjectURL após disparar o download", async () => {
    const buffer = bufferFromText("arquivo-para-baixar");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, headers: new Headers(), arrayBuffer: async () => buffer }),
    );
    const createObjectURLSpy = vi.fn().mockReturnValue("blob:fake-url");
    const revokeObjectURLSpy = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: createObjectURLSpy, revokeObjectURL: revokeObjectURLSpy });

    await downloadArtifactAsFile("https://api.example/artifacts/1/download", "scaffold.stl", { token: "t" });

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:fake-url");
    vi.unstubAllGlobals();
  });
});

describe("sanitizeFilename", () => {
  it("remove separadores de caminho para nunca escrever fora do nome de arquivo esperado", () => {
    expect(sanitizeFilename("../../etc/passwd")).not.toContain("/");
    expect(sanitizeFilename("..\\..\\windows\\system32")).not.toContain("\\");
  });

  it("nunca retorna vazio (usa um nome padrão de fallback)", () => {
    expect(sanitizeFilename("")).toBe("artefato");
  });
});
