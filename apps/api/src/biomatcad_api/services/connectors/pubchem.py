"""Conector PubChem PUG REST (Incremento 2.3, Rodada 2 -- Fases E e F).

Busca EXCLUSIVAMENTE por CID (nunca autocomplete, busca textual difusa ou scraping da
interface web), usando apenas o endpoint oficial documentado:

    https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/{campos}/JSON

Campos mapeados (apenas os estruturados e adequadamente compreendidos, listados
explicitamente na Fase F): CID, Title, IUPACName, MolecularFormula, MolecularWeight,
ConnectivitySMILES, SMILES, InChI, InChIKey, XLogP, TPSA, HBondDonorCount,
HBondAcceptorCount, RotatableBondCount, Charge, Complexity.

Correção da Run 3 do piloto Windows (2026-08-10, ver
docs/data/connectors/PUBCHEM_CONNECTOR.md): esta rodada pedia `CanonicalSMILES`/`IsomericSMILES`
-- os nomes de campo ANTIGOS do PUG REST, hoje DEPRECIADOS pelo PubChem (confirmado via
documentação oficial do PubChemPy, que reflete o mesmo mapeamento do PUG REST: "canonical_smiles
is deprecated, use connectivity_smiles instead" / "isomeric_smiles is deprecated, use smiles
instead"). A resposta real do PubChem durante a Run 3 confirmou isso na prática: os 3 CIDs
testados (2244/702/5090) retornaram sem as chaves `CanonicalSMILES`/`IsomericSMILES`, fazendo
ambas aparecerem em `missing_fields` para TODOS os CIDs -- nunca um problema pontual de um
composto específico. Corrigido solicitando os nomes ATUAIS (`ConnectivitySMILES` -- conectividade
apenas, sem estereoquímica/isótopos, substitui `CanonicalSMILES`; `SMILES` -- inclui
estereoquímica/isótopos, substitui `IsomericSMILES`). Os nomes semânticos internos
(`canonical_smiles`/`isomeric_smiles` em `NormalizedExternalRecord`) permanecem inalterados --
só a chave lida da resposta do PubChem mudou.

Nunca importa: segurança, toxicidade, indicação terapêutica, dose, posologia, ou qualquer
texto extenso de terceiros. Toda propriedade numérica calculada pelo PubChem é classificada
como `EvidenceType.CALCULATED` -- nunca `EXPERIMENTAL` sem evidência explícita disso. Campos
ausentes na resposta ficam `None` e são listados em `missing_fields`, nunca inventados como
zero ou string vazia. Ver docs/data/connectors/PUBCHEM_FIELD_MAPPING.md."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol

from biomatcad_api.config import get_settings
from biomatcad_api.models.scientific_data import EvidenceType
from biomatcad_api.models.scientific_ingestion import ParsingStatus
from biomatcad_api.services.connectors.base import (
    FetchResult,
    NormalizedExternalRecord,
    NormalizedProperty,
    ScientificDataConnector,
)
from biomatcad_api.services.connectors.http_client import (
    AllowlistedHttpsClient,
    HttpFetchResult,
    ResponseTooLargeError,
    UnexpectedRedirectError,
)


class _HttpClientLike(Protocol):
    """Forma mínima exigida de um cliente HTTP para este conector -- permite que os testes
    injetem um fake sem rede (sem herdar de `AllowlistedHttpsClient`), mantendo o tipo estático
    preciso (nunca `Any`) no construtor de `PubChemConnector`."""

    def get(self, path: str) -> HttpFetchResult: ...


PUBCHEM_ALLOWED_HOST = "pubchem.ncbi.nlm.nih.gov"

# Ordem fixa e explícita -- a mesma ordem usada na URL e na leitura da resposta. Qualquer campo
# adicionado no futuro precisa ser adicionado aqui E em normalize() explicitamente; nunca há
# descoberta automática de campos "extras" que a fonte possa retornar.
REQUESTED_PROPERTY_FIELDS = [
    "Title",
    "IUPACName",
    "MolecularFormula",
    "MolecularWeight",
    # ConnectivitySMILES/SMILES substituem os nomes depreciados CanonicalSMILES/IsomericSMILES
    # (ver docstring do módulo -- correção confirmada na Run 3 do piloto Windows, 2026-08-10).
    "ConnectivitySMILES",
    "SMILES",
    "InChI",
    "InChIKey",
    "XLogP",
    "TPSA",
    "HBondDonorCount",
    "HBondAcceptorCount",
    "RotatableBondCount",
    "Charge",
    "Complexity",
]

_MAX_CID_DIGITS = 12  # CIDs reais do PubChem hoje têm bem menos dígitos; limite generoso e seguro.


def _is_valid_cid(value: str) -> bool:
    return value.isdigit() and 1 <= len(value) <= _MAX_CID_DIGITS and int(value) > 0


class PubChemConnector(ScientificDataConnector):
    connector_id = "pubchem_pug_rest"
    connector_version = "0.1.0"
    primary_identifier_namespace = "pubchem_cid"
    schema_mapping_version = "pubchem_pug_rest_mapping_v1"

    def __init__(self, client: _HttpClientLike | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            settings = get_settings()
            self._client = AllowlistedHttpsClient(
                allowed_host=PUBCHEM_ALLOWED_HOST,
                user_agent=settings.pubchem_user_agent,
                contact_email=settings.pubchem_contact_email,
                rate_limit_per_second=settings.pubchem_rate_limit_per_second,
                timeout_seconds=settings.pubchem_timeout_seconds,
                max_retries=settings.pubchem_max_retries,
                max_response_bytes=200_000,
            )

    def validate_request(self, external_ids: list[str]) -> list[str]:
        errors: list[str] = []
        if not external_ids:
            errors.append("Lista de CIDs vazia -- é obrigatório fornecer ao menos um CID explícito.")
            return errors
        max_cids = get_settings().pubchem_max_cids_per_request
        if len(external_ids) > max_cids:
            errors.append(
                f"{len(external_ids)} CIDs solicitados, acima do limite máximo de {max_cids} por solicitação."
            )
        for cid in external_ids:
            if not _is_valid_cid(str(cid)):
                errors.append(f"CID inválido: {cid!r} (esperado um inteiro positivo em formato de texto).")
        return errors

    def _endpoint_path(self, cid: str) -> str:
        properties = ",".join(REQUESTED_PROPERTY_FIELDS)
        return f"/rest/pug/compound/cid/{cid}/property/{properties}/JSON"

    def fetch(self, external_id: str) -> FetchResult:
        path = self._endpoint_path(external_id)
        fetched_at = datetime.now(timezone.utc)

        try:
            result = self._client.get(path)
        except UnexpectedRedirectError as exc:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=0, content_type=None,
                fetched_at=fetched_at, payload_json=None, parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "unexpected_redirect", "message": str(exc)},
            )
        except ResponseTooLargeError as exc:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=0, content_type=None,
                fetched_at=fetched_at, payload_json=None, parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "response_too_large", "message": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 -- rede é inerentemente instável; sempre estruturado, nunca deixado propagar cru
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=0, content_type=None,
                fetched_at=fetched_at, payload_json=None, parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "network_error", "message": str(exc)},
            )

        if result.status_code == 404:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=404,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=None,
                parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "cid_not_found", "http_status": 404},
            )
        if result.status_code == 400:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=400,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=None,
                parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "bad_request", "http_status": 400},
            )
        if result.status_code != 200:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=result.status_code,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=None,
                parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "unexpected_status", "http_status": result.status_code},
            )

        try:
            payload = json.loads(result.body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=200,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=None,
                parsing_status=ParsingStatus.FAILED,
                parsing_error={"error_type": "invalid_json", "message": str(exc)},
            )

        properties = payload.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=200,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=payload,
                parsing_status=ParsingStatus.PARTIAL,
                parsing_error={"error_type": "empty_property_table"},
            )

        returned_cid = str(properties[0].get("CID", ""))
        if returned_cid != str(external_id):
            # "Confirmar os identificadores pela resposta oficial antes de persistir" (Fase I) --
            # uma resposta cujo CID não bate com o solicitado nunca é aceita como válida.
            return FetchResult(
                external_id=external_id, requested_endpoint=path, http_status=200,
                content_type=result.content_type, fetched_at=fetched_at, payload_json=payload,
                parsing_status=ParsingStatus.FAILED,
                parsing_error={
                    "error_type": "cid_mismatch",
                    "requested_cid": external_id,
                    "returned_cid": returned_cid,
                },
            )

        return FetchResult(
            external_id=external_id, requested_endpoint=path, http_status=200,
            content_type=result.content_type, fetched_at=fetched_at, payload_json=payload,
            parsing_status=ParsingStatus.PARSED,
        )

    def normalize(self, fetch_result: FetchResult) -> NormalizedExternalRecord:
        if fetch_result.payload_json is None:
            return NormalizedExternalRecord(
                external_identifier=fetch_result.external_id,
                source_name="PubChem",
                retrieved_at=fetch_result.fetched_at,
                missing_fields=list(REQUESTED_PROPERTY_FIELDS),
                mapping_warnings=["Nenhum payload disponível (fetch falhou) -- nenhum campo pôde ser normalizado."],
                raw_payload={},
            )

        properties_list = fetch_result.payload_json.get("PropertyTable", {}).get("Properties", [])
        props: dict = properties_list[0] if properties_list else {}

        missing_fields = [f for f in REQUESTED_PROPERTY_FIELDS if f not in props]
        mapping_warnings: list[str] = []
        calculated_properties: list[NormalizedProperty] = []

        def _map_numeric(pubchem_key: str, unit: str, property_key: str) -> None:
            raw_value = props.get(pubchem_key)
            if raw_value is None:
                return
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                mapping_warnings.append(
                    f"{pubchem_key} presente mas não numérico ({raw_value!r}); tratado como ausente, "
                    "nunca convertido/inventado."
                )
                return
            calculated_properties.append(
                NormalizedProperty(
                    property_key=property_key,
                    value_numeric=numeric_value,
                    value_text=None,
                    unit=unit,
                    evidence_type=EvidenceType.CALCULATED,
                )
            )

        _map_numeric("MolecularWeight", "g/mol", "molecular_weight")
        _map_numeric("XLogP", "dimensionless", "xlogp")
        _map_numeric("TPSA", "angstrom_squared", "tpsa")
        _map_numeric("HBondDonorCount", "count", "hbond_donor_count")
        _map_numeric("HBondAcceptorCount", "count", "hbond_acceptor_count")
        _map_numeric("RotatableBondCount", "count", "rotatable_bond_count")
        _map_numeric("Charge", "elementary_charge", "formal_charge")
        _map_numeric("Complexity", "dimensionless", "complexity")

        return NormalizedExternalRecord(
            external_identifier=fetch_result.external_id,
            source_name="PubChem",
            retrieved_at=fetch_result.fetched_at,
            preferred_name=props.get("Title"),
            iupac_name=props.get("IUPACName"),
            synonyms=[],
            formula=props.get("MolecularFormula"),
            inchi=props.get("InChI"),
            inchikey=props.get("InChIKey"),
            # ConnectivitySMILES substitui CanonicalSMILES (deprecado); SMILES substitui
            # IsomericSMILES (deprecado) -- ver docstring do módulo.
            canonical_smiles=props.get("ConnectivitySMILES"),
            isomeric_smiles=props.get("SMILES"),
            calculated_properties=calculated_properties,
            missing_fields=missing_fields,
            mapping_warnings=mapping_warnings,
            raw_payload=fetch_result.payload_json,
        )
