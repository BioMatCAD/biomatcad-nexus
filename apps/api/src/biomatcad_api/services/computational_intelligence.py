"""Módulo de inteligência computacional (Incremento 2.2, Seção 6).

Nesta rodada, apenas CONTRATOS, PONTOS DE EXTENSÃO e um mecanismo real de REGISTRO DE DECISÃO
são implementados -- nenhuma IA autônoma real propõe, executa ou ajusta parâmetros sozinha, e
nenhuma alegação de "equivalência ao Noyron" (software proprietário da LEAP 71, distinto do
PicoGK) é feita aqui ou em qualquer outro lugar do repositório.

O que É real e testável nesta rodada:
- `list_compatible_topology_providers`: consulta real ao registro de TopologyProvider
  (topology_providers.py) para listar o que HOJE está implementado -- não inventa
  compatibilidade fina de parâmetros.
- `compare_metrics_to_objectives`: aritmética simples e determinística (diferença absoluta,
  dentro/fora de tolerância) -- nunca um julgamento "inteligente" oculto.
- `build_manual_iteration_record`: monta um registro de decisão AUDITÁVEL e completo (entradas,
  proposta, execução, métricas, comparação, decisão, justificativa, algoritmo e versão) para uma
  iteração conduzida MANUALMENTE por um pesquisador humano hoje -- `algorithm_name` é sempre
  "manual-researcher-decision" nesta rodada, nunca um nome que sugira automação real.

O que NÃO é implementado nesta rodada (apenas o contrato `DesignAdvisor` existe, sem nenhuma
classe concreta que o implemente):
- seleção automática de topologia a partir de material/anatomia/restrições;
- proposta automática de parâmetros;
- execução automática de jobs;
- ajuste automático de parâmetros entre iterações.

Qualquer implementação futura de `DesignAdvisor` deve, no mínimo: (1) registrar-se
explicitamente (nunca ser descoberta por reflection/plugin, mesmo padrão de
TopologyProviderRegistry), (2) preservar `DesignIterationRecord` completo para toda decisão que
tomar, e (3) nunca substituir silenciosamente o fluxo manual já existente -- apenas propor,
nunca decidir sozinha sem revisão humana registrada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class DesignConstraints:
    """Entradas de um pedido de design: material, domínio e restrições/objetivos declarados.
    Puramente descritivo -- não valida nada além da forma dos próprios dados."""

    material_id: str | None
    domain_shape: str
    objectives: dict[str, float] = field(default_factory=dict)
    constraints_notes: str | None = None


@dataclass(frozen=True)
class DesignProposal:
    """Proposta de topologia + parâmetros para um pedido de design. Sempre inclui justificativa
    e fontes -- nunca uma sugestão sem explicação auditável. `proposed_by` identifica quem/o que
    propôs (ex.: "manual-researcher-decision"); nunca um rótulo genérico como "ai" ou "ia" sem
    identificar o algoritmo/versão real por trás."""

    topology_kind: str
    parameters: dict[str, Any]
    justification: str
    sources: list[str] = field(default_factory=list)
    proposed_by: str = "manual-researcher-decision"


@dataclass(frozen=True)
class ObjectiveComparison:
    """Comparação real entre uma métrica medida e um objetivo declarado -- sempre um fato
    calculável (diferença absoluta e checagem de tolerância), nunca um julgamento subjetivo
    automático."""

    objective_name: str
    target_value: float
    measured_value: float
    error_abs: float
    within_tolerance: bool
    tolerance: float


@dataclass(frozen=True)
class DesignIterationRecord:
    """Registro AUDITÁVEL de uma iteração de design -- o núcleo do "registro de decisão" pedido
    no escopo (Seção 6): "toda decisão deve registrar entradas, versão, restrições, evidências,
    algoritmo e resultado"."""

    iteration_number: int
    constraints: DesignConstraints
    proposal: DesignProposal
    executed_job_id: str | None
    measured_metrics: dict[str, Any] | None
    objective_comparisons: list[ObjectiveComparison]
    decision: str  # "accepted" | "rejected" | "adjusted" | "pending_execution"
    decision_justification: str
    algorithm_name: str
    algorithm_version: str
    created_at: str


class DesignAdvisor(Protocol):
    """Contrato para um futuro módulo de proposta/ajuste de parâmetros de design.

    NENHUMA implementação concreta existe nesta rodada -- apenas o ponto de extensão. Uma
    implementação futura real precisaria, no mínimo, destes três métodos, e nunca poderia ser
    descoberta automaticamente (mesmo princípio de não-reflection do TopologyProviderRegistry)."""

    def list_compatible_providers(self, constraints: DesignConstraints) -> list[str]:
        ...

    def propose_initial_parameters(self, constraints: DesignConstraints) -> DesignProposal:
        ...

    def propose_adjustment(
        self, constraints: DesignConstraints, previous_iteration: DesignIterationRecord
    ) -> DesignProposal:
        ...


def list_compatible_topology_providers(constraints: DesignConstraints) -> list[str]:
    """Único comportamento de "seleção" real desta rodada: lista quais providers de topologia
    estão REGISTRADOS E IMPLEMENTADOS (ver topology_providers.py) -- hoje sempre ["gyroid"].
    Não avalia compatibilidade fina de parâmetros contra `constraints` (isso é trabalho de um
    DesignAdvisor real futuro); apenas filtra pela lista de providers com status="implemented".
    `constraints` é recebido para manter a assinatura estável para quando essa filtragem fina
    existir, mas não é usado para nenhuma decisão nesta rodada."""
    from biomatcad_api.services.topology_providers import list_topology_providers

    del constraints  # não usado nesta rodada -- ver docstring
    return [p.kind for p in list_topology_providers() if p.status == "implemented"]


def compare_metrics_to_objectives(
    measured_metrics: dict[str, Any],
    objectives: dict[str, float],
    tolerance_pct_points: float = 2.0,
) -> list[ObjectiveComparison]:
    """Comparação real (aritmética simples, não uma "IA"): para cada objetivo declarado presente
    também em measured_metrics, calcula o erro absoluto e se está dentro da tolerância.
    Objetivos sem métrica medida correspondente são ignorados aqui -- quem chama decide o que
    fazer com objetivos não avaliáveis (nunca inventa um valor medido)."""
    comparisons: list[ObjectiveComparison] = []
    for name, target in objectives.items():
        if name not in measured_metrics:
            continue
        measured = float(measured_metrics[name])
        error = abs(measured - target)
        comparisons.append(
            ObjectiveComparison(
                objective_name=name,
                target_value=target,
                measured_value=measured,
                error_abs=error,
                within_tolerance=error <= tolerance_pct_points,
                tolerance=tolerance_pct_points,
            )
        )
    return comparisons


def build_manual_iteration_record(
    *,
    iteration_number: int,
    constraints: DesignConstraints,
    proposal: DesignProposal,
    executed_job_id: str | None,
    measured_metrics: dict[str, Any] | None,
    decision: str,
    decision_justification: str,
) -> DesignIterationRecord:
    """Constrói um registro de decisão completo para uma iteração conduzida MANUALMENTE por
    um pesquisador humano hoje -- não é um processo autônomo. `algorithm_name` é sempre
    "manual-researcher-decision" nesta rodada; qualquer futura automação real precisaria de um
    `algorithm_name` que identifique o algoritmo de verdade, nunca reaproveitar este valor."""
    comparisons = (
        compare_metrics_to_objectives(measured_metrics, constraints.objectives)
        if measured_metrics
        else []
    )
    return DesignIterationRecord(
        iteration_number=iteration_number,
        constraints=constraints,
        proposal=proposal,
        executed_job_id=executed_job_id,
        measured_metrics=measured_metrics,
        objective_comparisons=comparisons,
        decision=decision,
        decision_justification=decision_justification,
        algorithm_name="manual-researcher-decision",
        algorithm_version="1.0.0",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
