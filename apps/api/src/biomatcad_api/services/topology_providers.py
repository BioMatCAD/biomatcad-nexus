"""Registro real de provedores de topologia (Incremento 2.2, Seção 4: contrato `TopologyProvider`).

Abstração versionada e explícita que permite registrar novas topologias (outras TPMS, Voronoi,
híbridas, espacialmente graduadas) SEM alterar o fluxo de projeto/receita/job/artefato/
visualização -- apenas registrando uma nova entrada aqui e no registro equivalente do worker C#
(apps/geometry-worker/TopologyProviderRegistry.cs, mantido deliberadamente em sincronia manual;
um teste de regressão em ambos os lados trava os kinds/versões esperados).

Nesta rodada, apenas "gyroid" está IMPLEMENTADO: é o único kind aceito pelo JSON Schema
(schemas/biomatcem/geometry-recipe-v1.schema.json, topology.kind ainda é `"const": "gyroid"`) e
pelo worker real. "voronoi" já aparece aqui com status="planned" para deixar o contrato futuro
explícito e testável (rejeitado deliberadamente por get_topology_provider), mas não é aceito por
nenhuma receita real ainda -- ver docs/architecture/voronoi-topology-preparation.md para a
preparação técnica completa.

Esta checagem é DEFESA EM PROFUNDIDADE: o JSON Schema já impede topology.kind != "gyroid" de
chegar a uma receita validada; este registro é a segunda camada, consultada tanto na criação do
design run quanto na montagem do manifesto, e é o ÚNICO lugar que precisa mudar (junto do
registro C# equivalente) quando uma nova topologia for de fato implementada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProviderStatus = Literal["implemented", "planned"]


@dataclass(frozen=True)
class TopologyProviderInfo:
    kind: str
    provider_class: str
    version: str
    status: ProviderStatus
    description: str


class UnknownTopologyProviderError(Exception):
    """Levantado quando topology.kind não corresponde a nenhum provider registrado, ou
    corresponde a um provider com status='planned' (ainda não implementado -- rejeitar é o
    comportamento correto, nunca executar um provider inexistente)."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"Provider de topologia desconhecido ou não implementado: '{kind}'.")


# Fonte única de verdade sobre quais topologias este incremento realmente sabe executar.
# Adicionar uma nova topologia = adicionar uma entrada aqui (status="implemented" só depois de
# ter um provider C# real e testes passando -- nunca antes).
_REGISTRY: dict[str, TopologyProviderInfo] = {
    "gyroid": TopologyProviderInfo(
        kind="gyroid",
        provider_class="GyroidTopologyProvider",
        version="1.0.0",
        status="implemented",
        description=(
            "Superfície mínima periódica (TPMS) de Schoen (1970), domínio público. "
            "Implementação real em apps/geometry-worker/GyroidScaffoldBuilder.cs."
        ),
    ),
    "voronoi": TopologyProviderInfo(
        kind="voronoi",
        provider_class="VoronoiTopologyProvider",
        version="0.0.0-planned",
        status="planned",
        description=(
            "Preparação técnica documentada (sites, diagrama, grafo->struts, suavização de "
            "nós, recorte anatômico, calibração de porosidade) em "
            "docs/architecture/voronoi-topology-preparation.md -- execução real ainda NÃO "
            "implementada nesta rodada."
        ),
    ),
}


def list_topology_providers() -> list[TopologyProviderInfo]:
    """Todos os providers conhecidos, implementados ou planejados -- usado pelo painel de
    observabilidade/GUI para listar o que existe sem inventar nenhum estado."""
    return list(_REGISTRY.values())


def get_topology_provider(kind: str) -> TopologyProviderInfo:
    """Retorna o provider registrado E implementado para `kind`. Levanta
    UnknownTopologyProviderError para qualquer kind desconhecido OU ainda não implementado
    (status='planned') -- nunca deixa passar silenciosamente."""
    info = _REGISTRY.get(kind)
    if info is None or info.status != "implemented":
        raise UnknownTopologyProviderError(kind)
    return info
