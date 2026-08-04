"""Testes do módulo de inteligência computacional (Incremento 2.2, Seção 6).

Este módulo NÃO implementa nenhuma IA autônoma -- os testes aqui cobrem exatamente os três
comportamentos reais que existem (listar providers compatíveis via o registro real de
TopologyProvider, comparar métricas a objetivos com aritmética simples, e montar um registro de
decisão manual completo), e confirmam que o contrato DesignAdvisor permanece apenas um Protocol
sem implementação concreta nesta rodada.
"""
from __future__ import annotations

from biomatcad_api.services.computational_intelligence import (
    DesignConstraints,
    DesignIterationRecord,
    DesignProposal,
    build_manual_iteration_record,
    compare_metrics_to_objectives,
    list_compatible_topology_providers,
)


def test_list_compatible_topology_providers_reflete_o_registro_real():
    # Incremento 2.2 (rodada Voronoi): gyroid e voronoi_cell_edges_v1 estao ambos
    # implementados -- o mesmo registro consultado por geometry_job_service/manifest_service
    # (ver test_topology_providers.py). O placeholder "voronoi" (planned) continua de fora.
    constraints = DesignConstraints(material_id=None, domain_shape="block")
    result = list_compatible_topology_providers(constraints)
    assert result == ["gyroid", "voronoi_cell_edges_v1"]
    assert "voronoi" not in result


def test_compare_metrics_to_objectives_calcula_erro_real():
    comparisons = compare_metrics_to_objectives(
        measured_metrics={"porosity_pct_measured": 61.5, "volume_mm3": 400.0},
        objectives={"porosity_pct_measured": 60.0},
        tolerance_pct_points=2.0,
    )
    assert len(comparisons) == 1
    comp = comparisons[0]
    assert comp.objective_name == "porosity_pct_measured"
    assert comp.target_value == 60.0
    assert comp.measured_value == 61.5
    assert abs(comp.error_abs - 1.5) < 1e-9
    assert comp.within_tolerance is True


def test_compare_metrics_to_objectives_marca_fora_de_tolerancia():
    comparisons = compare_metrics_to_objectives(
        measured_metrics={"porosity_pct_measured": 78.8},
        objectives={"porosity_pct_measured": 60.0},
        tolerance_pct_points=2.0,
    )
    assert comparisons[0].within_tolerance is False


def test_compare_metrics_to_objectives_ignora_objetivo_sem_metrica_correspondente():
    # Nunca inventa um valor medido para um objetivo que não foi de fato medido.
    comparisons = compare_metrics_to_objectives(
        measured_metrics={"volume_mm3": 400.0},
        objectives={"porosity_pct_measured": 60.0},
    )
    assert comparisons == []


def test_build_manual_iteration_record_preserva_entradas_e_algoritmo_manual():
    constraints = DesignConstraints(
        material_id="mat-1", domain_shape="block", objectives={"porosity_pct_measured": 60.0}
    )
    proposal = DesignProposal(
        topology_kind="gyroid",
        parameters={"wall_thickness_mm": 0.4, "cell_size_mm": 2.0},
        justification="Receita ajustada manualmente pelo pesquisador com base na golden recipe block-gyroid-v1.",
        sources=["schemas/biomatcem/golden-recipes/block-gyroid-v1.json"],
    )
    record = build_manual_iteration_record(
        iteration_number=1,
        constraints=constraints,
        proposal=proposal,
        executed_job_id="job-123",
        measured_metrics={"porosity_pct_measured": 61.0},
        decision="accepted",
        decision_justification="Dentro da tolerância de 2 p.p.",
    )

    assert isinstance(record, DesignIterationRecord)
    # Nunca alega automação real -- sempre este valor fixo nesta rodada.
    assert record.algorithm_name == "manual-researcher-decision"
    assert record.algorithm_version == "1.0.0"
    assert record.constraints is constraints
    assert record.proposal is proposal
    assert record.executed_job_id == "job-123"
    assert record.decision == "accepted"
    assert len(record.objective_comparisons) == 1
    assert record.objective_comparisons[0].within_tolerance is True
    assert record.created_at  # timestamp real, não vazio


def test_build_manual_iteration_record_sem_metricas_medidas_ainda():
    # Cobre o estado "pending_execution" -- uma proposta pode ser registrada antes de ter
    # sido executada (nenhuma métrica ainda), e não deve fabricar uma comparação nesse caso.
    constraints = DesignConstraints(material_id=None, domain_shape="cylinder")
    proposal = DesignProposal(
        topology_kind="gyroid",
        parameters={"wall_thickness_mm": 0.5},
        justification="Proposta inicial baseada na golden recipe cylinder-gyroid-v1.",
    )
    record = build_manual_iteration_record(
        iteration_number=1,
        constraints=constraints,
        proposal=proposal,
        executed_job_id=None,
        measured_metrics=None,
        decision="pending_execution",
        decision_justification="Aguardando envio do job.",
    )
    assert record.executed_job_id is None
    assert record.measured_metrics is None
    assert record.objective_comparisons == []


def test_design_advisor_e_apenas_um_protocolo_sem_implementacao_concreta():
    # Regressão direta pedida no escopo: "nesta rodada, implemente apenas contratos ... não
    # fabrique uma IA autônoma fictícia". Confirma que as únicas classes públicas exportadas
    # pelo módulo são os 4 contratos de dados (dataclasses) e o próprio Protocol DesignAdvisor
    # -- nenhuma classe concreta que o implemente foi adicionada nesta rodada.
    import biomatcad_api.services.computational_intelligence as module

    expected_classes = {
        "DesignConstraints",
        "DesignProposal",
        "ObjectiveComparison",
        "DesignIterationRecord",
        "DesignAdvisor",
    }
    actual_classes = {
        name
        for name in dir(module)
        if not name.startswith("_")
        and isinstance(getattr(module, name), type)
        # Restringe a classes DEFINIDAS neste módulo -- exclui tipos apenas importados
        # (datetime, timezone, Protocol em si) que também aparecem em dir(module).
        and getattr(module, name).__module__ == module.__name__
    }
    assert actual_classes == expected_classes
