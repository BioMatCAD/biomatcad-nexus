import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type {
  PropertyDefinitionResponse,
  ScientificEntitySummary,
  ScientificEntityType,
  ScientificIdentifierResponse,
} from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { ReviewStatusBadge } from "../components/scientific/ScientificBadges";
import { ResearchOnlyDisclaimer } from "../components/scientific/ScientificDisclaimers";
import { PubChemIngestionPanel } from "../components/scientific/PubChemIngestionPanel";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const ENTITY_TYPE_LABEL: Record<ScientificEntityType, string> = {
  biomaterial: "biomaterial",
  chemical_substance: "substância química",
  drug: "fármaco",
  formulation: "formulação",
  nanomaterial: "nanomaterial",
  other: "outro",
};

const ADMIN_ROLES = new Set(["admin", "superadmin"]);

interface EnrichedRow {
  entity: ScientificEntitySummary;
  cid: string | null;
  inchikey: string | null;
  molecularWeight: number | null;
  molecularWeightUnit: string | null;
}

function findIdentifier(identifiers: ScientificIdentifierResponse[], namespace: string): string | null {
  const match = identifiers.find((i) => i.namespace === namespace);
  return match ? match.identifier : null;
}

export function ScientificDataPage() {
  const { token, user } = useAuth();
  const isAdmin = Boolean(user && ADMIN_ROLES.has(user.role));

  const [entities, setEntities] = useState<ScientificEntitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Record<string, EnrichedRow>>({});
  const [propertyDefinitions, setPropertyDefinitions] = useState<PropertyDefinitionResponse[] | null>(null);

  const [searchText, setSearchText] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [reviewFilter, setReviewFilter] = useState<string>("all");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .listScientificEntities(token)
      .then((data) => {
        if (!cancelled) setEntities(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao carregar dados científicos.");
      });
    client
      .listPropertyDefinitions(token)
      .then((defs) => {
        if (!cancelled) setPropertyDefinitions(defs);
      })
      .catch(() => {
        // Vocabulário de propriedades é apenas um complemento (massa molecular na listagem) --
        // sua ausência nunca deve bloquear a listagem principal de entidades.
        if (!cancelled) setPropertyDefinitions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Enriquecimento por linha (CID/InChIKey/massa molecular) -- feito em paralelo após a
  // listagem principal carregar; nunca bloqueia a listagem em si (cada linha mostra "—"
  // enquanto seu próprio enriquecimento está em andamento).
  useEffect(() => {
    if (!token || !entities || propertyDefinitions === null) return;
    const molecularWeightDefIds = new Set(
      propertyDefinitions.filter((d) => d.canonical_key === "molecular_weight").map((d) => d.id),
    );
    let cancelled = false;
    entities.forEach((entity) => {
      Promise.all([
        client.listEntityIdentifiers(token, entity.id),
        client.listEntityPropertyObservations(token, entity.id),
      ])
        .then(([identifiers, observations]) => {
          if (cancelled) return;
          const weightObs = observations.find(
            (o) => molecularWeightDefIds.has(o.property_definition_id) && o.value_numeric !== null,
          );
          setRows((prev) => ({
            ...prev,
            [entity.id]: {
              entity,
              cid: findIdentifier(identifiers, "pubchem_cid"),
              inchikey: findIdentifier(identifiers, "inchikey"),
              molecularWeight: weightObs?.value_numeric ?? null,
              molecularWeightUnit: weightObs?.unit_original ?? null,
            },
          }));
        })
        .catch(() => {
          // Falha de enriquecimento de UMA linha nunca derruba a listagem inteira -- a linha
          // simplesmente mantém os campos derivados como ausentes ("—").
        });
    });
    return () => {
      cancelled = true;
    };
  }, [token, entities, propertyDefinitions]);

  const filteredEntities = useMemo(() => {
    if (!entities) return null;
    return entities.filter((e) => {
      if (typeFilter !== "all" && e.entity_type !== typeFilter) return false;
      if (reviewFilter !== "all" && e.review_status !== reviewFilter) return false;
      if (searchText.trim().length > 0) {
        const needle = searchText.trim().toLowerCase();
        return e.preferred_name.toLowerCase().includes(needle);
      }
      return true;
    });
  }, [entities, typeFilter, reviewFilter, searchText]);

  return (
    <AuthenticatedLayout>
      <h1>Dados científicos</h1>
      <ResearchOnlyDisclaimer />
      <p style={{ color: "var(--color-text-secondary)" }}>
        Entidades científicas canônicas (biomateriais, substâncias químicas, fármacos, formulações,
        nanomateriais) com proveniência completa. Registros importados de fontes externas (ex.: PubChem)
        entram sempre como não revisados -- ver o rótulo de revisão de cada linha.
      </p>

      {isAdmin && <PubChemIngestionPanel />}

      <div style={styles.filterRow}>
        <label style={styles.filterLabel}>
          Buscar por nome
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="ex.: hidroxiapatita"
            aria-label="Buscar por nome"
            style={styles.input}
          />
        </label>
        <label style={styles.filterLabel}>
          Tipo
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="Filtrar por tipo"
            style={styles.input}
          >
            <option value="all">Todos</option>
            {Object.entries(ENTITY_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label style={styles.filterLabel}>
          Estado de revisão
          <select
            value={reviewFilter}
            onChange={(e) => setReviewFilter(e.target.value)}
            aria-label="Filtrar por estado de revisão"
            style={styles.input}
          >
            <option value="all">Todos</option>
            <option value="draft">Não revisado (draft)</option>
            <option value="reviewed">Revisado</option>
            <option value="rejected">Rejeitado</option>
          </select>
        </label>
      </div>

      {error && <ErrorState message={error} />}
      {!error && entities === null && <Loading label="Carregando dados científicos…" />}
      {!error && entities !== null && entities.length === 0 && (
        <EmptyState
          title="Nenhuma entidade científica cadastrada ainda"
          description="Rode o seed científico sintético (python -m biomatcad_api.seed_scientific_data) para popular esta lista."
        />
      )}
      {!error && filteredEntities !== null && entities !== null && entities.length > 0 && filteredEntities.length === 0 && (
        <EmptyState title="Nenhum resultado para os filtros aplicados" description="Ajuste a busca ou os filtros acima." />
      )}
      {!error && filteredEntities !== null && filteredEntities.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="scientific-entities-table">
          <thead>
            <tr>
              <th style={styles.th}>Nome</th>
              <th style={styles.th}>Tipo</th>
              <th style={styles.th}>PubChem CID</th>
              <th style={styles.th}>InChIKey</th>
              <th style={styles.th}>Massa molecular</th>
              <th style={styles.th}>Visibilidade</th>
              <th style={styles.th}>Revisão</th>
              <th style={styles.th}>Criado em</th>
            </tr>
          </thead>
          <tbody>
            {filteredEntities.map((entity) => {
              const row = rows[entity.id];
              return (
                <tr key={entity.id}>
                  <td style={styles.td}>
                    <Link to={`/app/scientific-data/${entity.id}`}>{entity.preferred_name}</Link>
                  </td>
                  <td style={styles.td}>{ENTITY_TYPE_LABEL[entity.entity_type] ?? entity.entity_type}</td>
                  <td style={styles.td} data-testid={`cid-${entity.id}`}>
                    {row?.cid ?? "—"}
                  </td>
                  <td style={styles.td} data-testid={`inchikey-${entity.id}`}>
                    {row?.inchikey ?? "—"}
                  </td>
                  <td style={styles.td} data-testid={`mw-${entity.id}`}>
                    {row?.molecularWeight !== null && row?.molecularWeight !== undefined
                      ? `${row.molecularWeight} ${row.molecularWeightUnit ?? ""}`.trim()
                      : "—"}
                  </td>
                  <td style={styles.td}>{entity.organization_id === null ? "global" : "da organização"}</td>
                  <td style={styles.td}>
                    <ReviewStatusBadge status={entity.review_status} />
                  </td>
                  <td style={styles.td}>{new Date(entity.created_at).toLocaleDateString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  th: { textAlign: "left", padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  filterRow: {
    display: "flex",
    gap: "var(--space-4)",
    flexWrap: "wrap",
    margin: "var(--space-4) 0",
  },
  filterLabel: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    fontSize: "0.85rem",
    color: "var(--color-text-secondary)",
  },
  input: {
    padding: "var(--space-2)",
    borderRadius: "var(--radius-sm)",
    border: "1px solid var(--color-border)",
    minWidth: "200px",
  },
};
