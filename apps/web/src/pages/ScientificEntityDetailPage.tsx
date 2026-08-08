import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type {
  BibliographicReferenceResponse,
  BiologicalEvidenceResponse,
  CrystalStructureReferenceResponse,
  IngestionConflictResponse,
  PropertyDefinitionResponse,
  PropertyObservationResponse,
  ProvenanceEntry,
  RawSourceRecordResponse,
  ReviewDecisionResponse,
  ScientificEntityDetail,
  ScientificIdentifierResponse,
  SupplierProductResponse,
} from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { EvidenceTypeBadge, ReviewStatusBadge } from "../components/scientific/ScientificBadges";
import { PubChemImportedDisclaimer, ResearchOnlyDisclaimer, SyntheticFixtureDisclaimer } from "../components/scientific/ScientificDisclaimers";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

type TabKey =
  | "overview"
  | "identifiers"
  | "properties"
  | "provenance"
  | "snapshots"
  | "references"
  | "biological-evidence"
  | "supplier-products"
  | "crystal-structures"
  | "conflicts"
  | "review-history";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Visão geral" },
  { key: "identifiers", label: "Identificadores" },
  { key: "properties", label: "Propriedades" },
  { key: "provenance", label: "Proveniência" },
  { key: "snapshots", label: "Snapshots" },
  { key: "references", label: "Referências" },
  { key: "biological-evidence", label: "Evidências biológicas" },
  { key: "supplier-products", label: "Produtos de fornecedor" },
  { key: "crystal-structures", label: "Estruturas cristalográficas" },
  { key: "conflicts", label: "Conflitos" },
  { key: "review-history", label: "Histórico de revisão" },
];

interface DetailData {
  entity: ScientificEntityDetail;
  identifiers: ScientificIdentifierResponse[];
  propertyObservations: PropertyObservationResponse[];
  propertyDefinitions: PropertyDefinitionResponse[];
  provenance: ProvenanceEntry[];
  rawSourceRecords: RawSourceRecordResponse[];
  biologicalEvidence: BiologicalEvidenceResponse[];
  supplierProducts: SupplierProductResponse[];
  crystalStructures: CrystalStructureReferenceResponse[];
  conflicts: IngestionConflictResponse[];
  reviewHistory: ReviewDecisionResponse[];
}

function isFromPubChemConnector(records: RawSourceRecordResponse[]): boolean {
  return records.some((r) => r.connector_id === "pubchem_pug_rest");
}

function isSyntheticFixture(records: RawSourceRecordResponse[]): boolean {
  return records.some((r) => r.connector_id === "synthetic_demo_connector");
}

export function ScientificEntityDetailPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const { token } = useAuth();
  const [data, setData] = useState<DetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  useEffect(() => {
    if (!token || !entityId) return;
    let cancelled = false;
    Promise.all([
      client.getScientificEntity(token, entityId),
      client.listEntityIdentifiers(token, entityId),
      client.listEntityPropertyObservations(token, entityId),
      client.listPropertyDefinitions(token),
      client.listEntityProvenance(token, entityId),
      client.listEntityRawSourceRecords(token, entityId),
      client.listEntityBiologicalEvidence(token, entityId),
      client.listEntitySupplierProducts(token, entityId),
      client.listEntityCrystalStructures(token, entityId),
      client.listEntityConflicts(token, entityId),
      client.listEntityReviewHistory(token, entityId),
    ])
      .then(
        ([
          entity,
          identifiers,
          propertyObservations,
          propertyDefinitions,
          provenance,
          rawSourceRecords,
          biologicalEvidence,
          supplierProducts,
          crystalStructures,
          conflicts,
          reviewHistory,
        ]) => {
          if (cancelled) return;
          setData({
            entity,
            identifiers,
            propertyObservations,
            propertyDefinitions,
            provenance,
            rawSourceRecords,
            biologicalEvidence,
            supplierProducts,
            crystalStructures,
            conflicts,
            reviewHistory,
          });
        },
      )
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao carregar entidade científica.");
      });
    return () => {
      cancelled = true;
    };
  }, [token, entityId]);

  const propertyDefById = useMemo(() => {
    const map = new Map<string, PropertyDefinitionResponse>();
    (data?.propertyDefinitions ?? []).forEach((d) => map.set(d.id, d));
    return map;
  }, [data]);

  const dedupedReferences = useMemo(() => {
    const seen = new Map<string, BibliographicReferenceResponse>();
    (data?.provenance ?? []).forEach((entry) => {
      if (entry.reference) seen.set(entry.reference.id, entry.reference);
    });
    return Array.from(seen.values());
  }, [data]);

  if (error) {
    return (
      <AuthenticatedLayout>
        <ErrorState message={error} />
      </AuthenticatedLayout>
    );
  }

  if (!data) {
    return (
      <AuthenticatedLayout>
        <Loading label="Carregando entidade científica…" />
      </AuthenticatedLayout>
    );
  }

  const { entity } = data;
  const fromPubChem = isFromPubChemConnector(data.rawSourceRecords);
  const syntheticFixture = isSyntheticFixture(data.rawSourceRecords);

  return (
    <AuthenticatedLayout>
      <h1>{entity.preferred_name}</h1>
      <ResearchOnlyDisclaimer />
      {fromPubChem && <PubChemImportedDisclaimer />}
      {syntheticFixture && <SyntheticFixtureDisclaimer />}

      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", margin: "var(--space-3) 0" }}>
        <ReviewStatusBadge status={entity.review_status} />
        <span style={{ fontSize: "0.85rem", color: "var(--color-text-secondary)" }}>
          {entity.organization_id === null ? "Registro global" : "Registro da organização"} · atualizado em{" "}
          {new Date(entity.updated_at).toLocaleString()}
        </span>
      </div>

      <nav aria-label="Abas de detalhe científico" style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", borderBottom: "1px solid var(--color-border)", marginBottom: "var(--space-4)" }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            aria-current={activeTab === tab.key ? "page" : undefined}
            style={{
              padding: "var(--space-2) var(--space-3)",
              border: "none",
              borderBottom: activeTab === tab.key ? "2px solid var(--color-accent)" : "2px solid transparent",
              background: "transparent",
              cursor: "pointer",
              fontWeight: activeTab === tab.key ? 700 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "overview" && (
        <section aria-label="Visão geral">
          <p>{entity.description ?? "Sem descrição."}</p>
          <p style={{ fontSize: "0.85rem", color: "var(--color-text-secondary)" }}>Tipo: {entity.entity_type}</p>
        </section>
      )}

      {activeTab === "identifiers" && (
        <section aria-label="Identificadores">
          {data.identifiers.length === 0 ? (
            <EmptyState title="Nenhum identificador externo registrado" />
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={styles.th}>Namespace</th>
                  <th style={styles.th}>Identificador</th>
                  <th style={styles.th}>Normalizado</th>
                  <th style={styles.th}>Verificação</th>
                </tr>
              </thead>
              <tbody>
                {data.identifiers.map((id) => (
                  <tr key={id.id}>
                    <td style={styles.td}>{id.namespace}</td>
                    <td style={styles.td}>{id.identifier}</td>
                    <td style={styles.td}>{id.identifier_normalized}</td>
                    <td style={styles.td}>{id.verification_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {activeTab === "properties" && (
        <section aria-label="Propriedades">
          {data.propertyObservations.length === 0 ? (
            <EmptyState title="Nenhuma observação de propriedade registrada" />
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="properties-table">
              <thead>
                <tr>
                  <th style={styles.th}>Nome</th>
                  <th style={styles.th}>Valor original</th>
                  <th style={styles.th}>Unidade original</th>
                  <th style={styles.th}>Valor normalizado</th>
                  <th style={styles.th}>Condições</th>
                  <th style={styles.th}>Método</th>
                  <th style={styles.th}>Incerteza</th>
                  <th style={styles.th}>Tipo de evidência</th>
                  <th style={styles.th}>Revisão</th>
                </tr>
              </thead>
              <tbody>
                {data.propertyObservations.map((obs) => {
                  const def = propertyDefById.get(obs.property_definition_id);
                  const conditionsParts: string[] = [];
                  if (obs.condition_temperature_k !== null) conditionsParts.push(`${obs.condition_temperature_k} K`);
                  if (obs.condition_pressure_kpa !== null) conditionsParts.push(`${obs.condition_pressure_kpa} kPa`);
                  if (obs.condition_ph !== null) conditionsParts.push(`pH ${obs.condition_ph}`);
                  if (obs.condition_medium) conditionsParts.push(obs.condition_medium);
                  return (
                    <tr key={obs.id}>
                      <td style={styles.td}>{def?.name ?? "—"}</td>
                      <td style={styles.td}>{obs.value_numeric ?? obs.value_text ?? "—"}</td>
                      <td style={styles.td}>{obs.unit_original}</td>
                      <td style={styles.td}>{obs.value_normalized ?? "—"}</td>
                      <td style={styles.td}>{conditionsParts.length > 0 ? conditionsParts.join(", ") : "—"}</td>
                      <td style={styles.td}>{obs.method ?? "—"}</td>
                      <td style={styles.td}>
                        {obs.uncertainty_low !== null || obs.uncertainty_high !== null
                          ? `${obs.uncertainty_low ?? "?"} — ${obs.uncertainty_high ?? "?"}`
                          : "—"}
                      </td>
                      <td style={styles.td}>
                        <EvidenceTypeBadge evidenceType={obs.evidence_type} />
                      </td>
                      <td style={styles.td}>
                        <ReviewStatusBadge status={obs.review_status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}

      {activeTab === "provenance" && (
        <section aria-label="Proveniência">
          {data.provenance.length === 0 ? (
            <EmptyState title="Nenhuma proveniência registrada" />
          ) : (
            <ul>
              {data.provenance.map((entry) => (
                <li key={entry.observation_id} data-testid="provenance-entry">
                  Observação {entry.observation_id}: fonte {entry.source?.name ?? "—"}
                  {entry.reference ? ` · referência: ${entry.reference.title}` : ""}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "snapshots" && (
        <section aria-label="Snapshots">
          {data.rawSourceRecords.length === 0 ? (
            <EmptyState title="Nenhum snapshot bruto associado a esta entidade" />
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="snapshots-table">
              <thead>
                <tr>
                  <th style={styles.th}>Conector</th>
                  <th style={styles.th}>Identificador externo</th>
                  <th style={styles.th}>Obtido em</th>
                  <th style={styles.th}>SHA-256</th>
                  <th style={styles.th}>Versão anterior</th>
                </tr>
              </thead>
              <tbody>
                {data.rawSourceRecords.map((r) => (
                  <tr key={r.id}>
                    <td style={styles.td}>{r.connector_id}</td>
                    <td style={styles.td}>{r.external_record_id}</td>
                    <td style={styles.td}>{new Date(r.fetched_at).toLocaleString()}</td>
                    <td style={styles.td} title={r.payload_sha256}>
                      {r.payload_sha256.slice(0, 12)}…
                    </td>
                    <td style={styles.td}>{r.predecessor_record_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {activeTab === "references" && (
        <section aria-label="Referências">
          {dedupedReferences.length === 0 ? (
            <EmptyState title="Nenhuma referência bibliográfica associada" />
          ) : (
            <ul>
              {dedupedReferences.map((ref) => (
                <li key={ref.id}>
                  {ref.title} {ref.doi ? `(DOI: ${ref.doi})` : ref.pmid ? `(PMID: ${ref.pmid})` : "(sem DOI/PMID)"}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "biological-evidence" && (
        <section aria-label="Evidências biológicas">
          {data.biologicalEvidence.length === 0 ? (
            <EmptyState title="Nenhuma evidência biológica registrada" />
          ) : (
            <ul>
              {data.biologicalEvidence.map((ev) => (
                <li key={ev.id}>
                  {ev.assay_type} ({ev.biological_model}) — {ev.endpoint}: {ev.result_value ?? ev.result_text ?? "—"}
                  {ev.research_classification_only && " · classificação apenas de pesquisa"}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "supplier-products" && (
        <section aria-label="Produtos de fornecedor">
          {data.supplierProducts.length === 0 ? (
            <EmptyState title="Nenhum produto de fornecedor vinculado" />
          ) : (
            <ul>
              {data.supplierProducts.map((p) => (
                <li key={p.id}>
                  {p.commercial_name} (SKU {p.catalog_sku})
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "crystal-structures" && (
        <section aria-label="Estruturas cristalográficas">
          {data.crystalStructures.length === 0 ? (
            <EmptyState title="Nenhuma estrutura cristalográfica registrada" />
          ) : (
            <ul>
              {data.crystalStructures.map((c) => (
                <li key={c.id}>
                  {c.database_name} / {c.accession_id} {c.formula ? `(${c.formula})` : ""}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "conflicts" && (
        <section aria-label="Conflitos">
          {data.conflicts.length === 0 ? (
            <EmptyState title="Nenhum conflito de ingestão registrado para esta entidade" />
          ) : (
            <ul data-testid="conflicts-list">
              {data.conflicts.map((c) => (
                <li key={c.id}>
                  {c.conflict_type} — CID {c.external_record_id}
                  {c.other_entity_id && ` (outra entidade: ${c.other_entity_id})`}
                  {!c.resolved && " · não resolvido"}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "review-history" && (
        <section aria-label="Histórico de revisão">
          {data.reviewHistory.length === 0 ? (
            <EmptyState title="Nenhuma decisão de revisão registrada ainda" />
          ) : (
            <ul>
              {data.reviewHistory.map((d) => (
                <li key={d.id}>
                  {d.decision} ({d.previous_state} → {d.new_state}) — {d.justification} em{" "}
                  {new Date(d.created_at).toLocaleString()}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  th: { textAlign: "left", padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
};
