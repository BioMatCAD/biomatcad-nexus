"""Testes do primeiro `DesignAdvisor` concreto (Incremento 2.2, rodada de fechamento, Fase B).

Cobre exatamente os cenários pedidos explicitamente: entradas válidas, dados incompletos,
limites, determinismo, ausência de alegação clínica, rastreabilidade das regras e a garantia
estrutural de isolamento por organização/projeto (o advisor é uma função pura sobre os dados
recebidos -- nunca lê banco, nunca compartilha estado entre chamadas).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from biomatcad_api.services.computational_intelligence import DesignConstraints
from biomatcad_api.services.design_advisor_rule_based import (
    GOLDEN_RECIPE_POROSITY_RANGE_PCT,
    NO_CLINICAL_VALIDATION_WARNING,
    RULE_MATERIAL_AVAILABILITY,
    RULE_POROSITY_RANGE,
    RULE_RESOLUTION_PRESENCE,
    RULE_TOPOLOGY_SELECTION,
    RULE_WALL_THICKNESS_CONSISTENCY,
    DesignAdvisorRequest,
    MaterialInfo,
    get_design_advisor,
    list_design_advisors,
)

GOLDEN_RECIPES_DIR = (
    Path(__file__).resolve().parents[3] / "schemas" / "biomatcem" / "golden-recipes"
)


def test_advisor_esta_registrado_explicitamente():
    # Mesmo principio do TopologyProviderRegistry: nao ha reflection/plugin, so lookup direto.
    assert list_design_advisors() == ["rule-based-v1"]
    assert get_design_advisor("rule-based-v1") is get_design_advisor("rule-based-v1")
    with pytest.raises(KeyError):
        get_design_advisor("advisor-inexistente")


def test_protocol_original_permanece_intacto_e_e_satisfeito_estruturalmente():
    # Nao usamos isinstance(..., DesignAdvisor) porque o Protocol original NAO e
    # @runtime_checkable (e nao deve ser alterado nesta rodada -- preservar o Protocol
    # existente). A conformidade e verificada estruturalmente: os 3 metodos do contrato
    # existem e sao chamaveis com a assinatura esperada.
    adv = get_design_advisor()
    assert hasattr(adv, "list_compatible_providers")
    assert hasattr(adv, "propose_initial_parameters")
    assert hasattr(adv, "propose_adjustment")

    constraints = DesignConstraints(material_id=None, domain_shape="block")
    providers = adv.list_compatible_providers(constraints)
    assert providers == ["gyroid", "voronoi_cell_edges_v1"]

    proposal = adv.propose_initial_parameters(constraints)
    assert proposal.topology_kind in providers
    assert proposal.proposed_by == "rule-based-v1"


def test_entrada_valida_completa_gera_recomendacao_de_alta_confianca():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(
        domain_shape="block",
        topology_kind="gyroid",
        target_porosity_pct=60.0,
        cell_size_mm=2.0,
        wall_thickness_mm=0.6,
        voxel_size_mm=0.2,
        material=MaterialInfo(
            material_id="mat-1", source="Material.properties no banco (id=mat-1)", properties={}
        ),
    )
    rec = adv.recommend(request)

    assert rec.recommended_topology_kind == "gyroid"
    assert rec.missing_fields == []
    assert rec.confidence_level == "high"
    assert rec.recommended_parameters["cell_size_mm"] == 2.0
    assert rec.advisor_id == "rule-based-v1"
    assert rec.generated_at  # timestamp real, nao vazio


def test_dados_incompletos_reduzem_confianca_e_listam_campos_ausentes():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(domain_shape="cylinder")
    rec = adv.recommend(request)

    assert rec.confidence_level == "low"
    assert set(rec.missing_fields) == {
        "target_porosity_pct",
        "voxel_size_mm",
        "material_properties",
        "cell_size_mm",
        "wall_thickness_mm",
    }
    # Nunca inventa a topologia -- ainda escolhe pela prioridade documentada.
    assert rec.recommended_topology_kind == "gyroid"


def test_topologia_invalida_nao_e_aceita_cai_para_fallback_documentado():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(domain_shape="block", topology_kind="voronoi")  # placeholder "planned"
    rec = adv.recommend(request)

    assert rec.recommended_topology_kind == "gyroid"
    assert any("não corresponde a nenhum provider implementado" in item for item in rec.limitations)


def test_limite_porosidade_fora_da_faixa_das_golden_recipes_e_sinalizado():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(domain_shape="block", target_porosity_pct=95.0)
    rec = adv.recommend(request)

    assert any("FORA da faixa" in rule.finding for rule in rec.triggered_rules if rule.rule_id == RULE_POROSITY_RANGE)
    assert any("fora da faixa" in item.lower() for item in rec.limitations)


def test_limite_wall_thickness_inconsistente_e_sinalizado_como_limitacao_nao_como_crash():
    adv = get_design_advisor()
    # Mesma regra fisica ja rejeitada pelo schema: wall_thickness_mm >= cell_size_mm / 2.
    request = DesignAdvisorRequest(domain_shape="block", cell_size_mm=2.0, wall_thickness_mm=1.5)
    rec = adv.recommend(request)

    assert any(rule.rule_id == RULE_WALL_THICKNESS_CONSISTENCY and "INCONSISTENTE" in rule.finding for rule in rec.triggered_rules)
    assert any("já é rejeitada pela validação real do schema" in item for item in rec.limitations)


def test_determinismo_mesma_entrada_produz_mesma_recomendacao():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(
        domain_shape="block",
        target_porosity_pct=60.0,
        cell_size_mm=2.0,
        wall_thickness_mm=0.6,
        voxel_size_mm=0.2,
    )
    rec1 = adv.recommend(request)
    rec2 = adv.recommend(request)

    # Compara tudo, exceto o timestamp (que varia por natureza -- gerado a cada chamada).
    assert rec1.recommended_topology_kind == rec2.recommended_topology_kind
    assert rec1.recommended_parameters == rec2.recommended_parameters
    assert rec1.justification == rec2.justification
    assert [r.rule_id for r in rec1.triggered_rules] == [r.rule_id for r in rec2.triggered_rules]
    assert rec1.confidence_level == rec2.confidence_level
    assert rec1.limitations == rec2.limitations
    assert rec1.missing_fields == rec2.missing_fields


def test_nunca_inventa_propriedade_de_material_sem_fonte_explicita():
    adv = get_design_advisor()
    # material_id sozinho (sem MaterialInfo) nao e reconhecido como "material disponivel".
    request = DesignAdvisorRequest(domain_shape="block")
    rec = adv.recommend(request)

    assert "material_properties" in rec.missing_fields
    assert not any(rule.rule_id == RULE_MATERIAL_AVAILABILITY for rule in rec.triggered_rules)
    # A limitacao esperada existe e explicita que nada foi inventado; nenhuma outra
    # limitacao no cenario faz qualquer afirmacao sobre propriedades de material.
    material_limitations = [lim for lim in rec.limitations if "material" in lim.lower()]
    assert len(material_limitations) == 1
    assert "nenhuma propriedade foi inventada" not in material_limitations[0]
    assert "sem qualquer suposição sobre propriedades" in material_limitations[0]


def test_material_explicito_e_reconhecido_sem_inventar_propriedades_extras():
    adv = get_design_advisor()
    material = MaterialInfo(
        material_id="mat-2",
        source="Material.properties no banco (id=mat-2)",
        properties={"young_modulus_gpa": 110.0},
    )
    request = DesignAdvisorRequest(domain_shape="block", material=material)
    rec = adv.recommend(request)

    assert "material_properties" not in rec.missing_fields
    assert any(rule.rule_id == RULE_MATERIAL_AVAILABILITY for rule in rec.triggered_rules)
    finding = next(rule.finding for rule in rec.triggered_rules if rule.rule_id == RULE_MATERIAL_AVAILABILITY)
    assert "nenhuma propriedade foi inventada" in finding
    # A recomendacao nunca copia as properties do material para os parametros recomendados --
    # isso seria inventar uma relacao material->parametro nao implementada nesta rodada.
    assert "young_modulus_gpa" not in rec.recommended_parameters


def test_material_com_source_vazia_nao_e_reconhecido_como_disponivel():
    # Mutation testing encontrou esta lacuna real: MaterialInfo com source="" (vazia) nao
    # deve ser tratado como "material disponivel" -- a fonte precisa ser identificada de
    # verdade, uma string vazia nao e uma proveniencia valida.
    adv = get_design_advisor()
    request = DesignAdvisorRequest(
        domain_shape="block", material=MaterialInfo(material_id="mat-3", source="")
    )
    rec = adv.recommend(request)

    assert "material_properties" in rec.missing_fields
    assert not any(rule.rule_id == RULE_MATERIAL_AVAILABILITY for rule in rec.triggered_rules)


def test_ausencia_de_alegacao_clinica_aviso_fixo_sempre_presente():
    adv = get_design_advisor()
    for request in (
        DesignAdvisorRequest(domain_shape="block"),
        DesignAdvisorRequest(domain_shape="cylinder", target_porosity_pct=60.0),
    ):
        rec = adv.recommend(request)
        assert rec.clinical_validation_warning == NO_CLINICAL_VALIDATION_WARNING
        assert "NÃO houve validação clínica" in rec.clinical_validation_warning

    # Nenhum texto de justificativa/limitacao em nenhum cenario testado usa vocabulario clinico
    # proibido (tratamento, diagnostico, prescricao, indicacao terapeutica).
    banned_terms = ("tratamento", "diagnóstic", "prescri", "terapêutic", "indicação clínica")
    all_text = " ".join(rec.justification + rec.limitations).lower()
    assert not any(term in all_text for term in banned_terms)


def test_rastreabilidade_cada_regra_disparada_aparece_com_id_estavel():
    adv = get_design_advisor()
    request = DesignAdvisorRequest(
        domain_shape="block",
        topology_kind="gyroid",
        target_porosity_pct=60.0,
        voxel_size_mm=0.2,
        material=MaterialInfo(material_id="mat-1", source="fonte-x"),
    )
    rec = adv.recommend(request)
    rule_ids = {rule.rule_id for rule in rec.triggered_rules}

    assert RULE_TOPOLOGY_SELECTION in rule_ids
    assert RULE_POROSITY_RANGE in rule_ids
    assert RULE_RESOLUTION_PRESENCE in rule_ids
    assert RULE_MATERIAL_AVAILABILITY in rule_ids
    # Toda regra disparada tem um finding nao vazio e rastreia a versao das regras.
    for rule in rec.triggered_rules:
        assert rule.finding
        assert rule.rules_version == "1.0.0"


def test_isolamento_estrutural_recomendacao_depende_apenas_da_propria_entrada():
    # O advisor nunca le banco/sessao/organizacao -- garante estruturalmente que uma
    # recomendacao para o "projeto/organizacao A" nao pode vazar dados de uma chamada anterior
    # para o "projeto/organizacao B": chamadas sucessivas com entradas diferentes nunca
    # compartilham estado (nenhum cache mutavel entre chamadas).
    adv = get_design_advisor()
    request_org_a = DesignAdvisorRequest(domain_shape="block", target_porosity_pct=60.0)
    request_org_b = DesignAdvisorRequest(domain_shape="cylinder", target_porosity_pct=95.0)

    rec_a = adv.recommend(request_org_a)
    rec_b = adv.recommend(request_org_b)
    rec_a_again = adv.recommend(request_org_a)

    assert rec_a.recommended_parameters != rec_b.recommended_parameters
    assert rec_a.missing_fields == rec_a_again.missing_fields
    assert rec_a.limitations == rec_a_again.limitations
    # Nenhum atributo de instancia mutavel foi introduzido pelo uso anterior.
    assert not vars(adv)


def test_golden_recipe_porosity_range_matches_constant():
    # Mantem a constante GOLDEN_RECIPE_POROSITY_RANGE_PCT honesta: recarrega as 6 golden
    # recipes reais do disco e falha se a faixa documentada no modulo ficar desalinhada com os
    # valores reais (evita "drift" silencioso entre a doc do modulo e os dados reais).
    files = sorted(GOLDEN_RECIPES_DIR.glob("*.json"))
    files = [f for f in files if f.name != "METADATA.json"]
    assert len(files) == 6, f"esperado 6 golden recipes, encontrado {len(files)}: {files}"

    porosities = []
    for f in files:
        data = json.loads(f.read_text())
        porosities.append(data["topology"]["target_porosity_pct"])

    assert min(porosities) == GOLDEN_RECIPE_POROSITY_RANGE_PCT[0]
    assert max(porosities) == GOLDEN_RECIPE_POROSITY_RANGE_PCT[1]


def test_ajuste_entre_iteracoes_nao_fabrica_otimizacao_automatica():
    # Nesta rodada, propose_adjustment reaplica a mesma proposta deterministica -- nao ha
    # heuristica de ajuste automatico implementada (evita fabricar uma alegacao de
    # "otimizacao automatica" inexistente).
    adv = get_design_advisor()
    constraints = DesignConstraints(material_id=None, domain_shape="block")
    initial = adv.propose_initial_parameters(constraints)
    adjusted = adv.propose_adjustment(constraints, previous_iteration=None)

    assert initial.topology_kind == adjusted.topology_kind
    assert initial.parameters == adjusted.parameters
