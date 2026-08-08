"""Registro explícito e não-reflexivo de conectores de ingestão científica (mesmo princípio de
`services/topology_providers.py::_REGISTRY` -- adicionar um conector novo = adicionar uma
entrada aqui, nunca descoberta automática/reflexão de módulos)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from biomatcad_api.services.connectors.base import ScientificDataConnector
from biomatcad_api.services.connectors.pubchem import PubChemConnector

ConnectorStatus = Literal["implemented", "planned"]


@dataclass(frozen=True)
class ConnectorInfo:
    connector_id: str
    connector_class: str
    version: str
    status: ConnectorStatus
    description: str


class UnknownConnectorError(Exception):
    def __init__(self, connector_id: str) -> None:
        self.connector_id = connector_id
        super().__init__(f"Conector desconhecido ou não implementado: '{connector_id}'.")


# Fonte única de verdade sobre quais conectores este incremento realmente sabe executar.
# "status='planned'" documenta candidatas futuras (ver docs/data/SOURCE_REGISTRY_POLICY.md)
# sem nenhuma implementação real -- nunca instanciadas.
_REGISTRY: dict[str, ConnectorInfo] = {
    "pubchem_pug_rest": ConnectorInfo(
        connector_id="pubchem_pug_rest",
        connector_class="PubChemConnector",
        version=PubChemConnector.connector_version,
        status="implemented",
        description=(
            "Conector piloto para PubChem PUG REST (Incremento 2.3, Rodada 2). Busca apenas "
            "por CID, apenas campos estruturados calculados/depositados -- ver "
            "docs/data/connectors/PUBCHEM_CONNECTOR.md."
        ),
    ),
    "chebi": ConnectorInfo(
        connector_id="chebi",
        connector_class="",
        version="",
        status="planned",
        description="Candidato futuro -- ver docs/data/SOURCE_REGISTRY_POLICY.md. Não implementado.",
    ),
    "chembl": ConnectorInfo(
        connector_id="chembl",
        connector_class="",
        version="",
        status="planned",
        description="Candidato futuro -- ver docs/data/SOURCE_REGISTRY_POLICY.md. Não implementado.",
    ),
    "crossref": ConnectorInfo(
        connector_id="crossref",
        connector_class="",
        version="",
        status="planned",
        description="Candidato futuro -- ver docs/data/SOURCE_REGISTRY_POLICY.md. Não implementado.",
    ),
    "crystallography_open_database": ConnectorInfo(
        connector_id="crystallography_open_database",
        connector_class="",
        version="",
        status="planned",
        description="Candidato futuro -- ver docs/data/SOURCE_REGISTRY_POLICY.md. Não implementado.",
    ),
    "rcsb_pdb": ConnectorInfo(
        connector_id="rcsb_pdb",
        connector_class="",
        version="",
        status="planned",
        description="Candidato futuro -- ver docs/data/SOURCE_REGISTRY_POLICY.md. Não implementado.",
    ),
}


def get_connector_info(connector_id: str) -> ConnectorInfo:
    info = _REGISTRY.get(connector_id)
    if info is None or info.status != "implemented":
        raise UnknownConnectorError(connector_id)
    return info


def get_connector(connector_id: str) -> ScientificDataConnector:
    info = get_connector_info(connector_id)
    if info.connector_id == "pubchem_pug_rest":
        return PubChemConnector()
    raise UnknownConnectorError(connector_id)  # pragma: no cover -- defesa em profundidade


def list_connectors() -> list[ConnectorInfo]:
    return list(_REGISTRY.values())
