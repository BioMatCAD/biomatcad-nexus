import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import { demoApiClient } from "../../api/demoClient";
import type { IngestionConflictResponse, IngestionRequestResponse, ScientificSourceResponse } from "../../api/types";
import { useAuth } from "../../context/AuthContext";
import { ErrorState } from "../feedback/ErrorState";
import { PubChemImportedDisclaimer } from "./ScientificDisclaimers";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const MAX_CIDS = 10;
const POLL_INTERVAL_MS = 2000;

const STATUS_LABEL: Record<string, string> = {
  queued: "na fila",
  running: "em execução",
  succeeded: "concluído",
  partial: "concluído parcialmente",
  failed: "falhou",
  cancelled: "cancelado",
};

function parseCids(raw: string): { cids: string[]; error: string | null } {
  const parts = raw
    .split(/[\s,]+/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
  if (parts.length === 0) {
    return { cids: [], error: null };
  }
  const nonNumeric = parts.filter((p) => !/^\d+$/.test(p));
  if (nonNumeric.length > 0) {
    return { cids: [], error: `CID(s) inválido(s), apenas números são aceitos: ${nonNumeric.join(", ")}` };
  }
  if (parts.length > MAX_CIDS) {
    return { cids: [], error: `No máximo ${MAX_CIDS} CIDs por solicitação (informados: ${parts.length}).` };
  }
  return { cids: parts, error: null };
}

export function PubChemIngestionPanel() {
  const { token } = useAuth();
  const [sources, setSources] = useState<ScientificSourceResponse[] | null>(null);
  const [sourceId, setSourceId] = useState<string>("");
  const [cidsInput, setCidsInput] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [activeRequest, setActiveRequest] = useState<IngestionRequestResponse | null>(null);
  const [conflicts, setConflicts] = useState<IngestionConflictResponse[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) return;
    client.listScientificSources(token).then((data) => {
      setSources(data);
      if (data.length > 0) setSourceId((prev) => prev || data[0].id);
    });
  }, [token]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // Polling controlado -- encerrado explicitamente ao desmontar o componente (nunca deixa um
  // intervalo órfão rodando após a página ser trocada).
  useEffect(() => stopPolling, [stopPolling]);

  const pollStatus = useCallback(
    (requestId: string) => {
      if (!token) return;
      stopPolling();
      pollTimerRef.current = window.setInterval(() => {
        client
          .getIngestionRequest(token, requestId)
          .then((req) => {
            setActiveRequest(req);
            if (["succeeded", "partial", "failed", "cancelled"].includes(req.status)) {
              stopPolling();
              if (req.status === "partial" || req.status === "succeeded") {
                client
                  .getIngestionRequestConflicts(token, requestId)
                  .then(setConflicts)
                  .catch(() => setConflicts([]));
              }
            }
          })
          .catch(() => {
            stopPolling();
          });
      }, POLL_INTERVAL_MS);
    },
    [token, stopPolling],
  );

  const handleCidsChange = (value: string) => {
    setCidsInput(value);
    const { error } = parseCids(value);
    setValidationError(error);
  };

  const submit = (dryRun: boolean) => {
    if (!token || !sourceId) return;
    const { cids, error } = parseCids(cidsInput);
    if (error) {
      setValidationError(error);
      return;
    }
    if (cids.length === 0) {
      setValidationError("Informe ao menos um CID.");
      return;
    }
    setSubmitError(null);
    setConflicts([]);
    const payload = { connector_id: "pubchem_pug_rest", source_id: sourceId, external_ids: cids, dry_run: dryRun };
    const call = dryRun ? client.submitIngestionDryRun(token, payload) : client.submitIngestionRequest(token, payload);
    call
      .then((req) => {
        setActiveRequest(req);
        pollStatus(req.id);
      })
      .catch((err) => {
        setSubmitError(err instanceof Error ? err.message : "Falha ao submeter solicitação de ingestão.");
      });
  };

  const cancel = () => {
    if (!token || !activeRequest) return;
    client
      .cancelIngestionRequest(token, activeRequest.id)
      .then((req) => setActiveRequest(req))
      .catch((err) => {
        setSubmitError(err instanceof Error ? err.message : "Falha ao cancelar solicitação.");
      });
  };

  const canCancel = activeRequest && ["queued", "running"].includes(activeRequest.status);
  const isBusy = activeRequest && ["queued", "running"].includes(activeRequest.status);

  return (
    <section
      aria-label="Painel administrativo de ingestão PubChem"
      data-testid="pubchem-ingestion-panel"
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        margin: "var(--space-4) 0",
      }}
    >
      <h2 style={{ marginTop: 0 }}>Ingestão PubChem (piloto administrativo)</h2>
      <PubChemImportedDisclaimer />
      <p style={{ color: "var(--color-text-secondary)", fontSize: "0.85rem" }}>
        Lista explícita de CIDs (números do PubChem), máximo {MAX_CIDS} por solicitação. Nunca busca por nome,
        nunca importação em massa.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", maxWidth: 480 }}>
        <label>
          Fonte (ScientificSource)
          <select
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            aria-label="Fonte científica"
            style={{ display: "block", width: "100%", padding: "var(--space-2)" }}
          >
            {(sources ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          CIDs (separados por vírgula ou espaço)
          <input
            type="text"
            value={cidsInput}
            onChange={(e) => handleCidsChange(e.target.value)}
            placeholder="ex.: 2244, 702, 5090"
            aria-label="Lista de CIDs"
            style={{ display: "block", width: "100%", padding: "var(--space-2)" }}
          />
        </label>

        {validationError && <ErrorState message={validationError} />}
        {submitError && <ErrorState message={submitError} />}

        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <button type="button" onClick={() => submit(true)} disabled={Boolean(isBusy) || !sourceId}>
            Dry-run
          </button>
          <button type="button" onClick={() => submit(false)} disabled={Boolean(isBusy) || !sourceId}>
            Submeter ingestão
          </button>
          {canCancel && (
            <button type="button" onClick={cancel}>
              Cancelar
            </button>
          )}
        </div>
      </div>

      {activeRequest && (
        <div data-testid="ingestion-request-status" style={{ marginTop: "var(--space-4)" }}>
          <p>
            <strong>Status:</strong> <span data-testid="ingestion-status-value">{STATUS_LABEL[activeRequest.status] ?? activeRequest.status}</span>
            {" · "}
            <strong>Correlation ID:</strong> <code>{activeRequest.id}</code>
            {activeRequest.dry_run && " · (dry-run — nenhuma entidade persistida)"}
          </p>
          {activeRequest.summary && (
            <ul>
              <li>Recebidos: {activeRequest.summary.received_count ?? "—"}</li>
              <li>Criados: {activeRequest.summary.created_count ?? "—"}</li>
              <li>Atualizados: {activeRequest.summary.updated_count ?? "—"}</li>
              <li>Inalterados: {activeRequest.summary.unchanged_count ?? "—"}</li>
              <li>Rejeitados: {activeRequest.summary.rejected_count ?? "—"}</li>
              <li>Conflitos: {activeRequest.summary.conflicts_count ?? "—"}</li>
            </ul>
          )}
          {activeRequest.error && (
            <ErrorState message={typeof activeRequest.error === "object" ? JSON.stringify(activeRequest.error) : String(activeRequest.error)} />
          )}
          {conflicts.length > 0 && (
            <div data-testid="ingestion-conflicts">
              <strong>Conflitos detectados:</strong>
              <ul>
                {conflicts.map((c) => (
                  <li key={c.id}>
                    {c.conflict_type} (CID {c.external_record_id})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
