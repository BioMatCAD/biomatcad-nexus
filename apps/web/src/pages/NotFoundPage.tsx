import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div style={{ padding: "var(--space-8)", textAlign: "center" }}>
      <h1>Página não encontrada</h1>
      <p>
        <Link to="/">Voltar ao início</Link>
      </p>
    </div>
  );
}
