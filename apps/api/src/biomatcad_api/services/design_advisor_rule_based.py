"""Primeira implementação CONCRETA do contrato `DesignAdvisor` (Incremento 2.2, rodada de
fechamento -- Fase B do plano de encerramento).

Este módulo NUNCA foi previsto como uma "IA de projeto" real -- é um mecanismo de REGRAS
determinísticas, versionadas, documentadas e testáveis, alinhado ao mesmo princípio de não-
-automação do restante do módulo de inteligência computacional
(`computational_intelligence.py`, docstring de topo). Ele:

- **Preserva intacto** o `Protocol DesignAdvisor` e os 4 contratos de dados originais em
  `computational_intelligence.py` (nenhuma linha desse arquivo foi alterada) -- inclusive o
  teste de regressão `test_design_advisor_e_apenas_um_protocolo_sem_implementacao_concreta`
  continua válido e passando, porque essa classe concreta vive neste módulo NOVO e separado,
  não em `computational_intelligence.py`.
- **Registra-se explicitamente** neste arquivo (`_ADVISOR_REGISTRY`, mesmo princípio de
  não-descoberta-automática/reflection do `TopologyProviderRegistry`,
  ver `topology_providers.py`) -- nenhum mecanismo de plugin/entry-point a descobre sozinho.
- **Nunca decide sozinha**: toda saída pública é uma `DesignAdvisorRecommendation`
  (recomendação), nunca uma ação aplicada automaticamente. O fluxo real de criação de projeto/
  receita/job continua exigindo uma ação explícita do pesquisador -- nada aqui envia jobs,
  grava receitas ou toma qualquer decisão persistente.
- **Nunca inventa propriedade de material**: só usa dados de material quando o chamador
  fornece um `MaterialInfo` explícito (com `source` identificada); `material_id` sozinho, sem
  esse objeto, é tratado como "material não caracterizado" e listado em `missing_fields` --
  nunca preenchido com um palpite ou valor de catálogo genérico.
- **Nunca prescreve medicamento, tratamento ou indicação clínica** -- o vocabulário de saída é
  estritamente geométrico/topológico/metodológico (topologia, parâmetros de malha, porosidade,
  confiança metodológica), nunca clínico.
- **Não depende de nenhum modelo externo de IA/ML** -- toda regra abaixo é aritmética simples,
  comparação de faixas ou lookup em tabelas estáticas versionadas neste arquivo.
- **Regras versionadas**: `RULES_VERSION` muda sempre que qualquer regra abaixo mudar de
  comportamento observável; cada recomendação registra `advisor_version` (RULES_VERSION no
  momento da chamada) para rastreabilidade.

Qualquer regra nova deve: (1) ter um `rule_id` único e estável, (2) documentar a fonte do
limiar/heurística usada (nunca um número inventado sem justificativa), (3) adicionar um teste
de determinismo e um teste de rastreabilidade (a regra precisa aparecer em `triggered_rules`
quando dispara).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from biomatcad_api.services.computational_intelligence import DesignAdvisor
from biomatcad_api.services.topology_providers import list_topology_providers

RULES_VERSION = "1.0.0"

ADVISOR_ID = "rule-based-v1"

# Aviso fixo, literal, repetido em TODA recomendação -- nunca omitido, nunca condicional.
NO_CLINICAL_VALIDATION_WARNING = (
    "Recomendação puramente metodológica/geométrica, gerada por regras determinísticas de "
    "pesquisa. NÃO houve validação clínica ou experimental. Não constitui indicação de "
    "tratamento, prescrição ou decisão clínica de qualquer tipo -- requer sempre revisão "
    "humana registrada antes de qualquer execução."
)

# Faixa de porosidade "tipicamente exercitada" -- derivada dos alvos REAIS das 6 golden
# recipes existentes nesta rodada (block-gyroid-v1: 60, cylinder-gyroid-v1: 55,
# preview-gyroid-low-res-v1: 60, block-voronoi-preview-v1: 65, block-voronoi-final-v1: 70,
# cylinder-voronoi-preview-v1: 60 -- ver schemas/biomatcem/golden-recipes/*.json). Não é uma
# alegação biológica/clínica de porosidade "ideal" -- é só o intervalo que este incremento já
# exercitou de fato com o worker PicoGK real. Um teste dedicado
# (test_design_advisor_rule_based.py::test_golden_recipe_porosity_range_matches_constant)
# recarrega os 6 arquivos reais e falha se esta constante ficar desalinhada.
GOLDEN_RECIPE_POROSITY_RANGE_PCT: tuple[float, float] = (55.0, 70.0)

# Prioridade documentada de seleção de topologia quando o pesquisador não especifica uma --
# ordem cronológica real de implementação/validação neste repositório (gyroid: Incremento
# 2.1.1 em diante; voronoi_cell_edges_v1: Incremento 2.2, rodada Voronoi) -- não uma alegação
# de superioridade científica entre as duas.
_DEFAULT_TOPOLOGY_PRIORITY: tuple[str, ...] = ("gyroid", "voronoi_cell_edges_v1")

RULE_TOPOLOGY_SELECTION = "DESIGN-ADVISOR-RULE-001"
RULE_POROSITY_RANGE = "DESIGN-ADVISOR-RULE-002"
RULE_RESOLUTION_PRESENCE = "DESIGN-ADVISOR-RULE-003"
RULE_MATERIAL_AVAILABILITY = "DESIGN-ADVISOR-RULE-004"
RULE_WALL_THICKNESS_CONSISTENCY = "DESIGN-ADVISOR-RULE-005"


@dataclass(frozen=True)
class MaterialInfo:
    """Só deve ser construído quando o chamador tem, de fato, dados de material identificados
    e disponíveis -- nunca um palpite. `source` é obrigatória e identifica a proveniência
    (ex.: "Material.properties no banco (id=...)", nunca um valor "typical"/"genérico")."""

    material_id: str
    source: str
    properties: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DesignAdvisorRequest:
    """Entradas permitidas nesta rodada (Fase B): domínio geométrico, topologia (opcional --
    ausência pede recomendação), porosidade-alvo, resolução, parâmetros de malha já propostos
    (para checagem de consistência, não para repeti-los sem análise) e métricas já medidas
    (opcional). Material só entra via `MaterialInfo` explícito."""

    domain_shape: str
    topology_kind: str | None = None
    target_porosity_pct: float | None = None
    cell_size_mm: float | None = None
    wall_thickness_mm: float | None = None
    voxel_size_mm: float | None = None
    measured_metrics: dict[str, Any] | None = None
    material: MaterialInfo | None = None


@dataclass(frozen=True)
class TriggeredRule:
    """Registro rastreável de uma regra que disparou -- sempre inclui o `rule_id` estável, a
    versão do conjunto de regras no momento e o achado concreto (nunca só "regra X disparou"
    sem dizer o quê)."""

    rule_id: str
    rules_version: str
    finding: str


@dataclass(frozen=True)
class DesignAdvisorRecommendation:
    """Saída pública e completa do advisor -- sempre uma recomendação, nunca uma decisão
    aplicada. `confidence_level` é estritamente METODOLÓGICO (qualidade/completude dos dados de
    entrada face às regras), nunca uma alegação de eficácia clínica ou biológica."""

    recommended_topology_kind: str
    recommended_parameters: dict[str, Any]
    justification: list[str]
    triggered_rules: list[TriggeredRule]
    confidence_level: str  # "low" | "medium" | "high"
    limitations: list[str]
    missing_fields: list[str]
    clinical_validation_warning: str
    advisor_id: str
    advisor_version: str
    generated_at: str


def _select_topology_kind(request: DesignAdvisorRequest) -> tuple[str, list[TriggeredRule], list[str]]:
    """Regra 001: se `topology_kind` foi informado, valida contra o registro real de
    TopologyProvider (nunca inventa um kind); se não foi informado, escolhe o primeiro kind
    'implemented' na prioridade documentada acima. Nunca recomenda um kind com
    status='planned' (ex.: o placeholder genérico 'voronoi')."""
    implemented = {p.kind for p in list_topology_providers() if p.status == "implemented"}
    limitations: list[str] = []

    if request.topology_kind is not None:
        if request.topology_kind not in implemented:
            limitations.append(
                f"topology_kind='{request.topology_kind}' não corresponde a nenhum provider "
                "implementado e registrado -- a recomendação abaixo usa o fallback padrão em "
                "vez do valor pedido."
            )
        else:
            rule = TriggeredRule(
                rule_id=RULE_TOPOLOGY_SELECTION,
                rules_version=RULES_VERSION,
                finding=f"topology_kind='{request.topology_kind}' confirmado como implementado e registrado.",
            )
            return request.topology_kind, [rule], limitations

    for kind in _DEFAULT_TOPOLOGY_PRIORITY:
        if kind in implemented:
            rule = TriggeredRule(
                rule_id=RULE_TOPOLOGY_SELECTION,
                rules_version=RULES_VERSION,
                finding=(
                    f"Nenhuma topologia válida foi especificada -- selecionado '{kind}' pela "
                    "prioridade documentada (ordem cronológica de implementação/validação)."
                ),
            )
            return kind, [rule], limitations

    # Nunca deveria ocorrer com o registro atual (sempre há ao menos 1 kind implementado) --
    # mas se ocorrer, é um erro real de configuração, não um valor inventado.
    raise RuntimeError(
        "Nenhum TopologyProvider com status='implemented' está registrado -- não há "
        "recomendação possível sem inventar uma topologia inexistente."
    )


def _check_porosity_range(request: DesignAdvisorRequest) -> tuple[list[TriggeredRule], list[str], list[str]]:
    """Regra 002: compara `target_porosity_pct` (se informado) contra a faixa realmente
    exercitada pelas golden recipes atuais -- fora da faixa não é rejeitado, é sinalizado como
    limitação metodológica (menos evidência empírica direta nesta rodada)."""
    rules: list[TriggeredRule] = []
    limitations: list[str] = []
    missing: list[str] = []

    if request.target_porosity_pct is None:
        missing.append("target_porosity_pct")
        return rules, limitations, missing

    low, high = GOLDEN_RECIPE_POROSITY_RANGE_PCT
    if low <= request.target_porosity_pct <= high:
        rules.append(
            TriggeredRule(
                rule_id=RULE_POROSITY_RANGE,
                rules_version=RULES_VERSION,
                finding=(
                    f"target_porosity_pct={request.target_porosity_pct} está dentro da faixa "
                    f"[{low}, {high}] já exercitada pelas golden recipes com o worker PicoGK real."
                ),
            )
        )
    else:
        rules.append(
            TriggeredRule(
                rule_id=RULE_POROSITY_RANGE,
                rules_version=RULES_VERSION,
                finding=(
                    f"target_porosity_pct={request.target_porosity_pct} está FORA da faixa "
                    f"[{low}, {high}] já exercitada pelas golden recipes."
                ),
            )
        )
        limitations.append(
            f"Porosidade-alvo fora da faixa [{low}, {high}]% já validada com o worker real "
            "nesta rodada -- resultado geométrico ainda plausível, mas sem evidência empírica "
            "direta de uma golden recipe equivalente."
        )
    return rules, limitations, missing


def _check_resolution(request: DesignAdvisorRequest) -> tuple[list[TriggeredRule], list[str], list[str]]:
    """Regra 003: presença de `voxel_size_mm`. Ausência não bloqueia a recomendação, apenas
    reduz a confiança metodológica e é listada em `missing_fields`."""
    if request.voxel_size_mm is not None:
        rule = TriggeredRule(
            rule_id=RULE_RESOLUTION_PRESENCE,
            rules_version=RULES_VERSION,
            finding=f"voxel_size_mm={request.voxel_size_mm} informado -- resolução considerada na confiança.",
        )
        return [rule], [], []
    return (
        [],
        ["Resolução (voxel_size_mm) não informada -- parâmetros de malha sugeridos têm confiança reduzida."],
        ["voxel_size_mm"],
    )


def _check_material_availability(request: DesignAdvisorRequest) -> tuple[list[TriggeredRule], list[str], list[str]]:
    """Regra 004: NUNCA inventa propriedade de material. Só reconhece material como
    'disponível' quando `request.material` é um `MaterialInfo` explícito com `source`
    identificada -- caso contrário, lista `material_properties` em `missing_fields` e segue
    sem qualquer alegação sobre o material."""
    if request.material is not None and request.material.source:
        rule = TriggeredRule(
            rule_id=RULE_MATERIAL_AVAILABILITY,
            rules_version=RULES_VERSION,
            finding=(
                f"Propriedades de material disponíveis e identificadas (fonte: "
                f"'{request.material.source}') -- nenhuma propriedade foi inventada, apenas as "
                "fornecidas explicitamente foram consideradas."
            ),
        )
        return [rule], [], []
    return (
        [],
        [
            (
                "Nenhum dado de material disponível foi fornecido -- a recomendação é puramente "
                "geométrica/topológica, sem qualquer suposição sobre propriedades mecânicas ou "
                "biológicas do material."
            )
        ],
        ["material_properties"],
    )


def _check_wall_thickness_consistency(
    request: DesignAdvisorRequest,
) -> tuple[list[TriggeredRule], list[str], list[str]]:
    """Regra 005: mesma restrição física já aplicada pelo JSON Schema/validação do backend
    (`wall_thickness_mm < cell_size_mm / 2` -- célula sem poro caso contrário, ver
    `recipe_service.py::_semantic_topology_errors` e o espelho em
    `recipeValidationOffline.ts`). Não inventa um novo limiar -- reaplica o mesmo já
    estabelecido e testado alhures."""
    if request.cell_size_mm is None or request.wall_thickness_mm is None:
        missing = []
        if request.cell_size_mm is None:
            missing.append("cell_size_mm")
        if request.wall_thickness_mm is None:
            missing.append("wall_thickness_mm")
        return (
            [],
            ["Parâmetros de malha (cell_size_mm/wall_thickness_mm) incompletos -- consistência geométrica não pôde ser checada."],
            missing,
        )

    limit = request.cell_size_mm / 2
    if request.wall_thickness_mm < limit:
        rule = TriggeredRule(
            rule_id=RULE_WALL_THICKNESS_CONSISTENCY,
            rules_version=RULES_VERSION,
            finding=(
                f"wall_thickness_mm={request.wall_thickness_mm} < cell_size_mm/2={limit} -- "
                "consistente com a restrição física já validada pelo schema (célula com poro)."
            ),
        )
        return [rule], [], []

    rule = TriggeredRule(
        rule_id=RULE_WALL_THICKNESS_CONSISTENCY,
        rules_version=RULES_VERSION,
        finding=(
            f"wall_thickness_mm={request.wall_thickness_mm} >= cell_size_mm/2={limit} -- "
            "INCONSISTENTE (mesma regra física rejeitada pelo schema/backend hoje)."
        ),
    )
    message = (
        f"wall_thickness_mm ({request.wall_thickness_mm}mm) >= cell_size_mm/2 ({limit}mm) -- "
        "essa combinação já é rejeitada pela validação real do schema; a receita final "
        "precisaria ajustar um dos dois valores antes de ser aceita."
    )
    return [rule], [message], []


class RuleBasedDesignAdvisor(DesignAdvisor):
    """Implementação concreta 'rule-based-v1' do `Protocol DesignAdvisor`. Implementa os 3
    métodos do contrato original (`list_compatible_providers`, `propose_initial_parameters`,
    `propose_adjustment`) para satisfazer o Protocol formalmente, e adiciona `recommend()`,
    o método rico usado de fato nesta rodada (recomendação estruturada completa)."""

    advisor_id = ADVISOR_ID
    advisor_version = RULES_VERSION

    def list_compatible_providers(self, constraints: Any) -> list[str]:
        from biomatcad_api.services.computational_intelligence import (
            list_compatible_topology_providers,
        )

        return list_compatible_topology_providers(constraints)

    def propose_initial_parameters(self, constraints: Any):
        from biomatcad_api.services.computational_intelligence import DesignProposal

        request = DesignAdvisorRequest(domain_shape=constraints.domain_shape)
        recommendation = self.recommend(request)
        return DesignProposal(
            topology_kind=recommendation.recommended_topology_kind,
            parameters=recommendation.recommended_parameters,
            justification="; ".join(recommendation.justification) or "Sem regras adicionais aplicáveis.",
            sources=[rule.rule_id for rule in recommendation.triggered_rules],
            proposed_by=self.advisor_id,
        )

    def propose_adjustment(self, constraints: Any, previous_iteration: Any):
        # Nenhum ajuste automático entre iterações nesta rodada -- reaplica a mesma proposta
        # inicial determinística; um ajuste real dependeria de heurísticas de otimização ainda
        # não implementadas (fora do escopo desta rodada, para não fabricar uma alegação de
        # "otimização automática" inexistente).
        return self.propose_initial_parameters(constraints)

    def recommend(self, request: DesignAdvisorRequest) -> DesignAdvisorRecommendation:
        """Método principal desta rodada: aplica as 5 regras documentadas no topo do módulo e
        monta uma `DesignAdvisorRecommendation` completa e rastreável."""
        topology_kind, topo_rules, topo_limitations = _select_topology_kind(request)
        porosity_rules, porosity_limitations, porosity_missing = _check_porosity_range(request)
        resolution_rules, resolution_limitations, resolution_missing = _check_resolution(request)
        material_rules, material_limitations, material_missing = _check_material_availability(request)
        wall_rules, wall_limitations, wall_missing = _check_wall_thickness_consistency(request)

        triggered_rules = [*topo_rules, *porosity_rules, *resolution_rules, *material_rules, *wall_rules]
        limitations = [*topo_limitations, *porosity_limitations, *resolution_limitations, *material_limitations, *wall_limitations]
        missing_fields = [*porosity_missing, *resolution_missing, *material_missing, *wall_missing]

        justification = [rule.finding for rule in triggered_rules]

        recommended_parameters: dict[str, Any] = {"topology_kind": topology_kind}
        if request.cell_size_mm is not None:
            recommended_parameters["cell_size_mm"] = request.cell_size_mm
        if request.wall_thickness_mm is not None:
            recommended_parameters["wall_thickness_mm"] = request.wall_thickness_mm
        if request.voxel_size_mm is not None:
            recommended_parameters["voxel_size_mm"] = request.voxel_size_mm
        if request.target_porosity_pct is not None:
            recommended_parameters["target_porosity_pct"] = request.target_porosity_pct

        # Confiança metodológica: começa "high", cai um nível a cada campo ausente relevante
        # (nunca uma pontuação numérica fabricada -- só 3 níveis discretos e documentados).
        confidence_level = "high"
        if len(missing_fields) >= 1:
            confidence_level = "medium"
        if len(missing_fields) >= 3:
            confidence_level = "low"

        return DesignAdvisorRecommendation(
            recommended_topology_kind=topology_kind,
            recommended_parameters=recommended_parameters,
            justification=justification,
            triggered_rules=triggered_rules,
            confidence_level=confidence_level,
            limitations=limitations,
            missing_fields=missing_fields,
            clinical_validation_warning=NO_CLINICAL_VALIDATION_WARNING,
            advisor_id=self.advisor_id,
            advisor_version=self.advisor_version,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


# Registro explícito -- mesmo princípio de não-reflection do TopologyProviderRegistry. Uma
# segunda implementação futura precisaria adicionar sua própria entrada aqui, nunca ser
# descoberta automaticamente.
_ADVISOR_REGISTRY: dict[str, RuleBasedDesignAdvisor] = {
    ADVISOR_ID: RuleBasedDesignAdvisor(),
}


def get_design_advisor(advisor_id: str = ADVISOR_ID) -> RuleBasedDesignAdvisor:
    """Retorna o advisor registrado para `advisor_id`. Levanta `KeyError` para qualquer id
    desconhecido -- nunca cai silenciosamente para um advisor diferente do pedido."""
    return _ADVISOR_REGISTRY[advisor_id]


def list_design_advisors() -> list[str]:
    return list(_ADVISOR_REGISTRY.keys())
