import { describe, expect, it, vi } from "vitest";
import { apiClient } from "../src/api/client";
import { ApiError } from "../src/api/types";

describe("apiClient", () => {
  it("faz parse de resposta de sucesso", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok" }) })
    );
    const result = await apiClient.health();
    expect(result).toEqual({ status: "ok" });
    vi.unstubAllGlobals();
  });

  it("lança ApiError tipado em resposta de erro", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ error: { id: "abc", code: "HTTP_403", message: "Proibido." } }),
      })
    );
    await expect(apiClient.health()).rejects.toBeInstanceOf(ApiError);
    vi.unstubAllGlobals();
  });
});
