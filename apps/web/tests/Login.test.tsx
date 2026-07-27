import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { SystemStatusProvider } from "../src/context/SystemStatusContext";
import { LoginPage } from "../src/pages/LoginPage";

describe("LoginPage", () => {
  it("renderiza os campos de e-mail e senha e permite digitar", async () => {
    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <AuthProvider>
          <SystemStatusProvider>
            <LoginPage />
          </SystemStatusProvider>
        </AuthProvider>
      </BrowserRouter>
    );

    const emailInput = screen.getByLabelText(/e-mail/i);
    const passwordInput = screen.getByLabelText(/senha/i);

    await user.type(emailInput, "demo@biomatcad.example");
    await user.type(passwordInput, "demo-synthetic-password-123");

    expect(emailInput).toHaveValue("demo@biomatcad.example");
    expect(passwordInput).toHaveValue("demo-synthetic-password-123");
  });

  it("mostra mensagem de erro quando o login falha", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: { id: "x", code: "HTTP_401", message: "Credenciais inválidas." } }),
      })
    );

    const user = userEvent.setup();
    render(
      <BrowserRouter>
        <AuthProvider>
          <SystemStatusProvider>
            <LoginPage />
          </SystemStatusProvider>
        </AuthProvider>
      </BrowserRouter>
    );

    await user.type(screen.getByLabelText(/e-mail/i), "errado@example.com");
    await user.type(screen.getByLabelText(/senha/i), "senha-errada");
    await user.click(screen.getByRole("button", { name: /^entrar$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/credenciais inválidas/i);
    vi.unstubAllGlobals();
  });
});
