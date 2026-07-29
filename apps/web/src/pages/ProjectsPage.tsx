import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { ProjectResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { EmptyState } from "../components/feedback/EmptyState";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

export function ProjectsPage() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    if (!token) return;
    client
      .listProjects(token)
      .then(setProjects)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar projetos."));
  };

  useEffect(load, [token]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !name.trim()) return;
    setCreating(true);
    try {
      await client.createProject(token, { name: name.trim() });
      setName("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar projeto.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <AuthenticatedLayout>
      <h1>Projetos BioMatCAD</h1>

      <form onSubmit={handleCreate} style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
        <label htmlFor="project-name" className="visually-hidden">
          Nome do projeto
        </label>
        <input
          id="project-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nome do novo projeto"
        />
        <button type="submit" disabled={creating || !name.trim()}>
          Criar projeto
        </button>
      </form>

      {error && <ErrorState message={error} />}
      {!error && projects === null && <Loading label="Carregando projetos…" />}
      {!error && projects !== null && projects.length === 0 && (
        <EmptyState title="Nenhum projeto ainda" description="Crie o primeiro projeto acima." />
      )}
      {!error && projects !== null && projects.length > 0 && (
        <ul>
          {projects.map((p) => (
            <li key={p.id}>
              <Link to={`/app/projects/${p.id}`}>{p.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </AuthenticatedLayout>
  );
}
