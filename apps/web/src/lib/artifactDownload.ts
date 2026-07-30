// Download autenticado de artefatos (Incremento 2.2 -- "consolidar visualizador 3D", Seção 2).
//
// Corrige o achado real da auditoria (docs/architecture/viewer-3d-audit.md): o visualizador e
// os links de download da lista de artefatos usavam a URL crua da API sem nunca anexar o
// header Authorization -- funcionava apenas no modo demo (arquivo estático público, sem auth
// real) e nunca foi exercitado contra um backend real com autenticação de verdade.
//
// Este módulo:
// - nunca insere o token na URL (sempre via header Authorization: Bearer, igual a client.ts);
// - usa AbortController para permitir cancelamento real do carregamento;
// - valida o tamanho declarado (Content-Length, quando presente) contra um limite configurável
//   ANTES de ler o corpo inteiro -- evita consumo descontrolado de memória com um arquivo
//   inesperadamente grande;
// - calcula o SHA-256 dos bytes recebidos via SubtleCrypto e permite ao chamador comparar
//   com o checksum já conhecido (Artifact.sha256, obtido antes do download pela API) -- uma
//   divergência é reportada como erro explícito, nunca ignorada silenciosamente;
// - nunca usa `<a href>` estático para artefatos que exigem autenticação -- o chamador deve
//   pedir um Blob/ObjectURL (ver `downloadArtifactAsFile`) e revogar o ObjectURL logo depois
//   de disparar o download.

export class ArtifactTooLargeError extends Error {
  constructor(
    public readonly declaredBytes: number,
    public readonly maxBytes: number,
  ) {
    super(
      `Artefato (${declaredBytes.toLocaleString("pt-BR")} bytes) excede o limite configurado de ` +
        `${maxBytes.toLocaleString("pt-BR")} bytes para carregamento direto no visualizador.`,
    );
    this.name = "ArtifactTooLargeError";
  }
}

export class ArtifactChecksumMismatchError extends Error {
  constructor(
    public readonly expectedSha256: string,
    public readonly actualSha256: string,
  ) {
    super(
      "Checksum do artefato baixado não confere com o registrado pela API -- o arquivo pode " +
        "estar corrompido ou ter sido alterado. O download foi rejeitado por segurança.",
    );
    this.name = "ArtifactChecksumMismatchError";
  }
}

export interface FetchArtifactOptions {
  token?: string | null;
  signal?: AbortSignal;
  maxBytes?: number;
  /** SHA-256 esperado (de `ArtifactResponse.sha256`), verificado após o download quando informado. */
  expectedSha256?: string;
}

export interface FetchArtifactResult {
  buffer: ArrayBuffer;
  sha256: string;
}

export async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Baixa um artefato de forma autenticada, validando tamanho e checksum. Nunca renderiza/entrega
 * bytes parciais ou substitutos em caso de falha -- sempre rejeita (throw) explicitamente. */
export async function fetchArtifactBuffer(url: string, options: FetchArtifactOptions = {}): Promise<FetchArtifactResult> {
  const headers = new Headers();
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const response = await fetch(url, { headers, signal: options.signal });
  if (!response.ok) {
    throw new Error(`Falha ao baixar artefato (status ${response.status}).`);
  }

  const contentLengthHeader = response.headers.get("Content-Length");
  if (options.maxBytes && contentLengthHeader) {
    const declared = Number.parseInt(contentLengthHeader, 10);
    if (Number.isFinite(declared) && declared > options.maxBytes) {
      throw new ArtifactTooLargeError(declared, options.maxBytes);
    }
  }

  const buffer = await response.arrayBuffer();

  if (options.maxBytes && buffer.byteLength > options.maxBytes) {
    // Backend não declarou Content-Length (ou mentiu) -- valida de novo depois de ler, mesmo
    // já tendo pago o custo de memória desta leitura; ainda assim nunca prossegue para o parse.
    throw new ArtifactTooLargeError(buffer.byteLength, options.maxBytes);
  }

  const actualSha256 = await sha256Hex(buffer);
  if (options.expectedSha256 && actualSha256 !== options.expectedSha256) {
    throw new ArtifactChecksumMismatchError(options.expectedSha256, actualSha256);
  }

  return { buffer, sha256: actualSha256 };
}

/** Dispara o download de um artefato para o disco do usuário via Blob/ObjectURL autenticado --
 * substitui o padrão anterior de `<a href={url} download>` sem autenticação. O ObjectURL é
 * revogado logo após o clique programático, nunca deixado vivo indefinidamente (vazamento de
 * memória do navegador). */
export async function downloadArtifactAsFile(
  url: string,
  filename: string,
  options: FetchArtifactOptions = {},
): Promise<void> {
  const { buffer } = await fetchArtifactBuffer(url, options);
  const blob = new Blob([buffer], { type: "application/octet-stream" });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = sanitizeFilename(filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/** Sanitização mínima de nome de arquivo (Seção 6 do escopo): remove separadores de caminho e
 * caracteres de controle -- nunca usa o nome bruto de um campo vindo da API diretamente no DOM
 * como atributo `download` sem passar por aqui. */
export function sanitizeFilename(name: string): string {
  // eslint-disable-next-line no-control-regex -- remoção intencional de caracteres de controle do nome de arquivo
  return name.replace(/[/\\]/g, "_").replace(/[\x00-\x1f]/g, "").slice(0, 200) || "artefato";
}
