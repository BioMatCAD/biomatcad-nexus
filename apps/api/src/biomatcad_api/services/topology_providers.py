"""Registro real de provedores de topologia (Incremento 2.2, Seção 4: contrato `TopologyProvider`).

Abstração versionada e explícita que permite registrar novas topologias (outras TPMS, Voronoi,
híbridas, espacialmente graduadas) SEM alterar o fluxo de projeto/receita/job/artefato/
visualização -- apenas registrando uma nova entrada aqui e no registro equivalente do worker C#
(apps/geometry-worker/TopologyProviderRegistry.cs, mantido deliberadamente em sincronia manual;
um teste de regressão em ambos os lados trava os kinds/versões esperados).

"gyroid" e "voronoi_cell_edges_v1" estão IMPLEMENTADOS: são os dois kinds aceitos pelo JSON
Schema (schemas/biomatcem/geometry-recipe-v1.schema.json, topology é um oneOf entre os dois) e
pelo worker real (Incremento 2.2, rodada Voronoi, Seção 8 -- ver
apps/geometry-worker/VoronoiTopologyProvider.cs/VoronoiScaffoldBuilder.cs). "voronoi" (nome
genérico, sem sufixo de versão) permanece deliberadamente como um placeholder reservado com
status="planned" -- um possível ponto de extensão futuro (ex.: uma variante anatomy_guided ou
uma estratégia alternativa de suavização), nunca implementado nesta rodada e nunca confundido com
"voronoi_cell_edges_v1" (a estratégia real e concreta implementada: struts sobre as ARESTAS REAIS
de uma tesselação de Voronoi 3D, ver docs/architecture/voronoi-cell-edges-v1-math-audit.md).

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
            "Placeholder reservado e genérico (sem sufixo de versão) -- NÃO é a implementação "
            "real desta rodada (ver 'voronoi_cell_edges_v1' abaixo). Mantido como ponto de "
            "extensão futuro (ex.: uma segunda estratégia de topologia baseada em Voronoi)."
        ),
    ),
    "voronoi_cell_edges_v1": TopologyProviderInfo(
        kind="voronoi_cell_edges_v1",
        provider_class="VoronoiTopologyProvider",
        version="0.1.0",
        status="implemented",
        description=(
            "Primeira vertical real de Voronoi (Incremento 2.2): struts construídos sobre as "
            "ARESTAS REAIS das células de uma tesselação de Voronoi 3D limitada pelo domínio "
            "(nunca um grafo de adjacência de sítios de Delaunay -- ver distinção matemática "
            "completa em docs/architecture/voronoi-cell-edges-v1-math-audit.md). Implementação "
            "real em apps/geometry-worker/VoronoiScaffoldBuilder.cs/VoronoiTopologyProvider.cs. "
            "Execução real do PicoGK ainda não verificada neste sandbox Linux -- ver "
            "ADR-0007/roteiro de validação Windows."
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
