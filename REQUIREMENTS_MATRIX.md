# Matriz de Requisitos — BioMatCAD Nexus (Fase 0)

Requisitos extraídos integralmente dos dois documentos-fonte auditados (ver
`docs/SOURCE_DOCUMENTS.md` para hashes, páginas e proveniência completa). Colunas conforme
Seção 4.2 do Prompt Mestre: requisito, fonte/página, interpretação, prioridade, risco,
critério de aceite, status.

Convenção de prioridade: **P0** crítico ao MVP vertical (Seção 28 do Prompt Mestre), **P1**
necessário à visão da tese, **P2** desejável/evolução. Status inicial de todos os itens:
**Backlog** — nada foi implementado ou verificado nesta sessão.

## A. Requisitos com base direta na Apresentação (`AP-`)

| ID | Requisito | Fonte/página | Interpretação | Prioridade | Risco | Critério de aceite | Status |
|---|---|---|---|---|---|---|---|
| AP-01 | Plataforma deve reduzir ciclo de design de biomaterial de meses para horas | Slide 1 | Meta de desempenho de processo, não requisito de UI | P1 | Alegação de "~95%" carece de medição própria; não reproduzir como fato sem benchmark interno | Medir tempo real de um ciclo completo na plataforma e comparar com literatura citada, com metodologia documentada | Backlog |
| AP-02 | Integrar CAD 3D, FEM, banco de materiais e IA local em plataforma única | Slide 2 | Requisito arquitetural central | P0 | Acoplamento excessivo entre módulos se não houver contratos claros | Os 4 módulos citados existem como componentes integráveis com interface definida (API ou biblioteca) | Backlog |
| AP-03 | ML local via Ollama (porta 11434) e LM Studio (porta 1234), sem API externa | Slide 2, 3 | Requisito de privacidade/soberania de dados | P0 | Portas fixas hardcoded são frágeis; devem ser configuráveis | Inferência funcional local, sem chamadas de rede externas, com portas configuráveis | Backlog |
| AP-04 | Otimização multiobjetivo com frente de Pareto para β-TCP (resistência × porosidade × bioatividade) | Slide 2, 4 | Caso de uso concreto de otimização | P0 | Modelo de bioatividade prevista pode não ter dado suficiente | NSGA-II executa e produz frente de Pareto navegável para os 3 objetivos citados | Backlog |
| AP-05 | Validação por comparação com literatura e ensaios mecânicos (DLP, robocasting) | Slide 2 | Requisito de validação científica | P1 | Ensaios experimentais fora do escopo apenas-computacional descrito na Tese §8.1 | Existir protocolo formal de comparação numérica × literatura, com registro de erro/incerteza | Backlog |
| AP-06 | Stack declarada do estado atual: Python, PyQt5, SQLite, PicoGK C#, Ollama/LM Studio, GGUF, Marching Cubes, PyInstaller | Slide 3 | Descreve o app **já existente**, não uma proposta nova | P0 | Divergente da arquitetura React/API REST da Tese §2 — ver `ARCH-DIVERGE-01` | ADR decide se PyQt5 é preservado como cliente científico (Prompt Mestre §6.1) | Backlog |
| AP-07 | Banco de materiais: 32+ materiais, 43+ referências DOI (β-TCP, HAp, BCP, vidros 45S5/13-93, Ti-6Al-4V, CoCr, PLA/PCL/PLGA) | Slide 3 | Estado atual do banco, ponto de partida real (não os "200+" da meta da Tese) | P0 | Confundir estado atual (32+) com meta futura (200+, Tese §7.1) | Banco importável/auditável com todas as 43+ referências DOI verificáveis | Backlog |
| AP-08 | Arquiteturas TPMS: Gyroid, Schwarz-P, IWP; modelo Gibson-Ashby (E*/Es=C·ρ̄ⁿ, n=2); Weibull m≈4,39 (DLP) | Slide 3, 4 | Requisitos de geometria e modelo mecânico | P0 | Constantes (n, m) são específicas de condição de ensaio — não universalizar (Seção 5 do Prompt Mestre) | Geração paramétrica dos 3 TPMS com registro de proveniência de cada constante usada | Backlog |
| AP-09 | Módulo DICOM "equivalente a InVesalius (32 func.)"; CrystalDB Downloader (COD ~450k + PDB ~200k, catálogo SQLite) | Slide 4 | Componentes já existentes segundo o autor | P1 | "Equivalente a InVesalius" é comparação informal, não certificação de paridade funcional — não repetir como alegação de equivalência formal | Inventariar as 32 funções DICOM reais e testar o CrystalDB Downloader contra as duas bases | Backlog |

## B. Requisitos com base direta na Proposta de Tese (`TP-`)

| ID | Requisito | Fonte/página | Interpretação | Prioridade | Risco | Critério de aceite | Status |
|---|---|---|---|---|---|---|---|
| TP-01 | Arquitetura cliente-servidor: backend Python, frontend web React.js, 6 módulos via API REST | §2, p.2 | Arquitetura-alvo proposta (não implementada) | P0 | Contradiz stack desktop da Apresentação — decisão arquitetural pendente | ADR registrada e aprovada antes de qualquer código de frontend | Backlog |
| TP-02 | 6 módulos: CAD 3D Engine, FEM Simulator, Materials Database, ML Predictor, Multi-Objective Optimizer, Visualization UI | §2, p.2 | Escopo funcional nuclear do doutorado | P0 | Sobreposição com módulos já existentes no app PyQt5 — mapear antes de recriar | Cada módulo tem contrato de API/dados definido e pelo menos um fluxo E2E funcional | Backlog |
| TP-03 | Fluxo iterativo de 4–8h por ciclo: requisitos → design paramétrico → simulação → validação/exportação | §3.1, p.3 | Pipeline operacional do BioMat Constructor (Seção 15 do Prompt Mestre) | P0 | Tempo de 4–8h é meta, não medido | Pipeline executa fim-a-fim ao menos uma vez com tempo registrado | Backlog |
| TP-04 | 7 fases de execução ao longo de 48 meses (revisão → CAD/BD → FEM → ML → otimização → integração/validação → documentação) | §3.2, p.3 | Cronograma acadêmico do doutorado, não sprint de engenharia de software | P1 | Confundir prazo acadêmico (anos) com prazo de entrega de software (Prompt Mestre pede incrementos revisáveis) | Roadmap de engenharia mapeado às 7 fases acadêmicas, com marcos de software próprios | Backlog |
| TP-05 | Otimização multiobjetivo com NSGA-II; objetivos: resistência mecânica, porosidade, biocompatibilidade, custo estimado | §5, p.5–6 | Requisito técnico de otimização | P0 | "Custo estimado de produção" carece de modelo de custo definido | NSGA-II implementado com os 4 objetivos e frente de Pareto exportável | Backlog |
| TP-06 | ML de predição biológica: dataset >500 amostras da literatura; RF/SVM/redes neurais; k-fold k=5; métricas R²/MAE/RMSE; export pickle/ONNX | §6, p.6–7 | Pipeline científico de ML (Seção 18.1 do Prompt Mestre) | P0 | Dataset ainda não compilado; vazamento de dados entre splits é risco conhecido | Dataset versionado + split sem vazamento + métricas reportadas com IC | Backlog |
| TP-07 | Banco de dados estruturado com >200 materiais caracterizados (meta) | §7.1, p.7 | Meta de produto ao final do doutorado, não estado atual | P2 | Ver AP-07 — não confundir com os 32+ atuais | Contagem de materiais no banco com proveniência completa por item | Backlog |
| TP-08 | Modelos de ML "validados (acurácia > 85%)" | §7.1, p.7 | Meta de aceite do projeto de tese | P1 | Prompt Mestre §18.1 explicitamente proíbe fixar acurácia isolada como único critério — usar métricas por tipo de problema | Critério de aceite reescrito para conjunto de métricas (sensibilidade/especificidade/AUROC/calibração ou R²/MAE/RMSE conforme o caso), não só acurácia | Backlog |
| TP-09 | Repositório GitHub open-source com documentação; manual técnico e tutoriais | §7.1, p.7 | Requisito de entrega/documentação | P1 | — | Repositório público com README, manual e licença definidos | Backlog |
| TP-10 | Registro de software no INPI | §7.2, p.7 | Requisito de propriedade intelectual, fora do escopo técnico direto | P2 | Depende de decisão institucional/jurídica, não de código | Acompanhar como item administrativo separado do backlog de engenharia | Backlog |
| TP-11 | ≥3 artigos Qualis A1-B1; apresentações em congressos (CBBTEC, SBF, MRS, TMS) | §7.2, p.7 | Produto acadêmico, não requisito de software | P2 | — | Fora do escopo de engenharia; apenas rastrear como marco acadêmico | N/A (acadêmico) |
| TP-12 | Viabilidade técnica justificada por "abordagem computacional, sem dependência de laboratórios" | §8.1, p.8 | **Delimitação explícita de escopo pelo próprio candidato/orientação**: o projeto de tese não inclui laboratório físico | P0 (como restrição) | Alto — Prompt Mestre §12 (LIMS/ELN/terapia celular) contradiz esta delimitação; ver `SCOPE-CONFLICT-01` | Decisão explícita do usuário sobre incluir ou não o escopo de laboratório/clínica antes de gerar requisitos dessas seções | **Resolvido em 2026-07-27: usuário optou por seguir o escopo completo do Prompt Mestre (ver Decisão de Escopo abaixo)** |
| TP-13 | Ineditismo: ausência de plataforma similar integrando CAD+FEM+ML+Otimização para biomateriais ortopédicos, com interface para não-programadores | §8.3, p.8 | Requisito de UX (usuário não-programador) e de posicionamento | P1 | Alegação de ineditismo não foi verificada nesta sessão (não há busca de literatura concorrente registrada) | Revisão de literatura/mercado documentada antes de reafirmar ineditismo publicamente | Backlog |
| TP-14 | 40 referências bibliográficas com DOI/periódico/ano, cobrindo biomateriais, FEM, materials informatics, otimização evolutiva | §9, p.9–11 | Base de evidências científicas iniciais para `EvidenceSet` (Seção 15.1 do Prompt Mestre) | P0 | — | As 40 referências carregadas no banco de evidências com metadado completo (autor, ano, periódico, DOI quando disponível) | Backlog |

## C. Requisitos do Prompt Mestre sem base nos documentos-fonte (`PM-ONLY-`)

Estes itens vêm exclusivamente do Prompt Mestre (Seções 9–12: identidade/clínica, plataforma
clínica digital, telemedicina, LIMS/ELN/terapia celular). **Nenhum aparece na tese ou na
apresentação.** Continuam marcados com `Fonte: Prompt Mestre (sem base documental)` — a
decisão de escopo abaixo confirma que devem entrar no backlog, não que passaram a ter
respaldo científico/acadêmico nos dois documentos auditados.

| ID | Requisito (resumo) | Fonte | Status |
|---|---|---|---|
| PM-ONLY-01 | Prontuário eletrônico, FHIR, agenda clínica, portal do paciente | Prompt Mestre §10 (não consta na tese/apresentação) | `CONFIRMED-PRODUCT-SCOPE` — Backlog de implementação, Fase 6 |
| PM-ONLY-02 | Telemedicina/WebRTC, videoconferência segura | Prompt Mestre §11 (não consta na tese/apresentação) | `CONFIRMED-PRODUCT-SCOPE` — Backlog de implementação, Fase 6 |
| PM-ONLY-03 | LIMS, ELN, biobanco, terapia celular, chain of custody/identity | Prompt Mestre §12 (não consta na tese/apresentação) | `CONFIRMED-PRODUCT-SCOPE` — Backlog de implementação, Fase 5 |
| PM-ONLY-04 | Identidade (Keycloak/OIDC), RBAC/ABAC com 17 perfis institucionais | Prompt Mestre §9 (não consta na tese/apresentação) | `CONFIRMED-PRODUCT-SCOPE` — parcialmente iniciado (ver subitens `PM-ONLY-04a` a `PM-ONLY-04h` abaixo) |
| PM-ONLY-05 | Matriz regulatória (Anvisa SaMD, ISO 13485/14971, IEC 62304/62366-1) | Prompt Mestre §24 (não consta na tese/apresentação) | `CONFIRMED-PRODUCT-SCOPE` — Backlog de implementação, Fase 7 |

**Nota de rastreabilidade (ADR-0003):** `CONFIRMED-PRODUCT-SCOPE` significa que o requisito é
válido para o produto BioMatCAD Nexus por decisão explícita do usuário em 2026-07-27. Não
significa que a tese ou a apresentação descrevem, validam ou aprovam esse requisito — a coluna
Fonte continua apontando exclusivamente para o Prompt Mestre, por honestidade de proveniência
(Prompt Mestre §3.1: não atribuir aos documentos científicos afirmações que eles não
apresentam).

## D. Subitens de PM-ONLY-04 (identidade) — status após Incremento 1.1

| ID | Item | Status | Evidência |
|---|---|---|---|
| PM-ONLY-04a | Classificação explícita do modo de autenticação atual | **Implementado** | `AUTH_MODE="DEV_AUTH"` exposto em `GET /api/v1/system/status.auth_mode`; ver ADR-0005 |
| PM-ONLY-04b | Recusa de startup com segredo JWT ausente/inseguro fora de teste | **Implementado** | `Settings.assert_secure_for_environment()`, testado em `test_dev_auth_startup.py` (5 testes) |
| PM-ONLY-04c | Autorização mínima para ações administrativas | **Implementado (mínimo, não é RBAC completo)** | `require_admin` (`role in {admin, superadmin}`), sem hierarquia institucional/projeto |
| PM-ONLY-04d | Auditoria de login, falha, logout, tentativa de alteração de estado | **Implementado** | `AuditEvent` para `login_succeeded/failed`, `logout`, `operational_state_activation_denied`, `admin_action_denied`, `clinical_suite_activated/deactivated` |
| PM-ONLY-04e | OIDC/OAuth 2.1 com Authorization Code + PKCE | Backlog | Nenhum código; `services/identity/` vazio |
| PM-ONLY-04f | MFA (TOTP) e WebAuthn/passkeys | Backlog | Nenhum código |
| PM-ONLY-04g | Step-up authentication para ações sensíveis | Backlog | Hoje a suíte clínica exige apenas papel admin + chave mestra, sem step-up de fato |
| PM-ONLY-04h | RBAC/ABAC completo com os 17 perfis institucionais, revogação real de sessão, painel de sessões ativas, refresh token | Backlog | `User.role` é uma string simples; `/auth/logout` é simbólico (sem blocklist) — ver ADR-0005 |

## E. Correções do Incremento 1.1 (rastreabilidade de bug)

| ID | Achado | Correção | Evidência |
|---|---|---|---|
| FIX-1.1-01 | `clinical_suite_enabled` somava Laboratório aos três flags clínicos e usava lógica OR em vez de AND | Recalculado via `get_effective_states`/`CLINICAL_SUITE_KINDS`, exigindo os três simultaneamente, excluindo Laboratório | `test_clinical_suite_is_independent_from_laboratory`, ADR-0004 |
| FIX-1.1-02 | Endpoint único permitia ativar `clinical_pilot`/`clinical_production` individualmente, sem atomicidade nem segunda verificação | `POST /operational-state/activate` agora rejeita (400) os 3 kinds clínicos; endpoints dedicados `/clinical-suite/activate|deactivate` garantem atomicidade | `test_clinical_kinds_rejected_on_independent_endpoint`, `test_activation_rolls_back_completely_on_failure` |
| FIX-1.1-03 | Nenhuma verificação de autorização de administrador na ativação de estados | `require_admin` adicionado a todos os endpoints de ativação, com auditoria de tentativas negadas | `test_laboratory_activation_denied_for_non_admin`, `test_activation_denied_for_non_admin_user` |
| FIX-1.1-04 | Autenticação não classificada explicitamente; sem checagem de segredo no startup | `AUTH_MODE="DEV_AUTH"` + `assert_secure_for_environment()` | ADR-0005, `test_dev_auth_startup.py` |
| FIX-1.1-05 | Sem mecanismo de expiração para estados operacionais | `expires_at` + `is_effectively_enabled()` (avaliação em tempo de leitura) | `test_clinical_suite_expiration_is_respected` |

## Decisão de escopo (registrada em 2026-07-27, refinada por ADR-0003)

O Prompt Mestre é a especificação autoritativa do produto BioMatCAD Nexus. A tese e a
apresentação são fontes científicas e históricas do núcleo computacional, mas não definem nem
limitam o escopo total da plataforma. Os módulos `PM-ONLY-*` estão `CONFIRMED-PRODUCT-SCOPE`.
Consequências registradas para rastreabilidade:

- A frase da Tese §8.1 ("abordagem computacional, sem dependência de laboratórios") descreve a
  viabilidade do trabalho acadêmico de doutorado especificamente, não uma proibição de expansão
  futura da plataforma — ver ADR-0003. Não é mais tratada como conflito de escopo, e sim como
  fontes complementares com finalidades diferentes (validação científica vs. especificação de
  produto).
- Toda menção pública/institucional ao sistema deve continuar distinguindo o núcleo com base
  científica (`AP-*`, `TP-*`) do envelope confirmado apenas pelo Prompt Mestre (`PM-ONLY-*`),
  para não sugerir que o comitê de orientação da tese avaliou cientificamente o escopo
  clínico/laboratorial — essa distinção é sobre proveniência da evidência, não sobre validade
  do requisito de produto.
- Módulos `PM-ONLY-*` herdam os princípios inegociáveis do Prompt Mestre (Seção 3): quatro
  estados operacionais (Pesquisa/Laboratório/Piloto clínico/Produção clínica), uso clínico
  bloqueado por padrão, nenhuma alegação de conformidade regulatória sem validação externa.
- Ver ADR-0001 (`docs/adr/0001-escopo-completo-prompt-mestre.md`) e ADR-0003
  (`docs/adr/0003-interpretacao-escopo-vs-tese.md`).

## F. Incremento 2.1 (Fase 2) — vertical geométrica funcional do núcleo BioMatCAD

Primeiro incremento que toca diretamente requisitos científicos (`AP-*`/`TP-*`), não apenas
fundação/segurança. Escopo restrito à vertical executável material → projeto → receita
BioMatCEM → job → worker C#/PicoGK → scaffold Gyroid → métricas → artefatos → visualização 3D —
sem FEM, DICOM, LIMS, prontuário ou funcionalidades clínicas (fora de escopo deliberado deste
incremento). A tabela abaixo já reflete as correções do Incremento 2.1.1 (corretivo, sem
mudança de escopo — ver `IMPLEMENTATION_STATUS.md` para o detalhamento item a item).

| ID | Requisito relacionado | O que foi implementado nesta sessão | Status |
|---|---|---|---|
| AP-08 (parcial) | Arquiteturas TPMS: Gyroid, Schwarz-P, IWP | Apenas Gyroid, em domínio block/cylinder. Schema versionado (`schemas/biomatcem/geometry-recipe-v1.schema.json`), worker C#/PicoGK implementado e compilado (`apps/geometry-worker`), fórmula de Schoen (1970) implementada em `GyroidMath.cs` (núcleo matemático puro, independente de PicoGK — 48 testes xUnit no Incremento 2.1.1) e aplicada via `GyroidDomainImplicit` em `GyroidScaffoldBuilder.cs` (o antigo `GyroidImplicit.cs` do Incremento 2.1 não existe mais como arquivo separado). Incremento 2.1.1 corrigiu o recorte do domínio cilíndrico (SDF real, não bounding box), a semântica espessura/isovalor (ADR-0008) e a calibração de porosidade — tudo testado matematicamente, nenhum contra PicoGK real. **Execução real continua bloqueada** neste sandbox (ausência de runtime nativo PicoGK linux-x64) — ver ADR-0007 | **Parcialmente implementado, execução bloqueada com evidência** |
| TP-02 (parcial) | Módulo "CAD 3D Engine" | Camada de dados (`GeometryRecipe`, `DesignRun`, `GeometryJob`), orquestração de job via fila Postgres, worker separado da API, cálculo de métricas geométricas (bounding box, volume, área de superfície, watertight) sobre malhas de teste. Geração real de scaffold via PicoGK não verificada (mesmo bloqueio de AP-08) | **Parcialmente implementado, execução bloqueada com evidência** |
| AP-07 / TP-07 (parcial) | Banco de materiais com propriedades rastreáveis e referências DOI | Modelo de dados real (`MaterialRecord`, `MaterialProperty`, `ScientificReference`) com valor/unidade/fonte/DOI/método/incerteza/versão/status de revisão por propriedade — mas **sem dados de materiais carregados** nesta sessão (nenhuma propriedade foi inventada; catálogo começa vazio, pronto para receber os 32+ materiais citados em AP-07 num próximo incremento) | **Schema/API implementados; catálogo de dados ainda vazio** |

Novas entidades de dados (9): `MaterialRecord`, `MaterialProperty`, `ScientificReference`,
`BioMatProject`, `GeometryRecipe`, `DesignRun`, `GeometryJob`, `Artifact`, `ArtifactManifest` —
migração Alembic aplicada e verificada contra banco vazio e banco populado (`apps/api/alembic/
versions/97983fbc0288_*.py`).

Testes: 65 testes pytest coletados no backend (64 executados + 1 skip esperado do worker real quando dotnet não está no PATH), incluindo 15 testes de schema JSON; 17 testes
Vitest (frontend), 9 testes xunit (C#, apenas código independente de PicoGK). Ver
`TEST_EVIDENCE.md` para o log bruto desta sessão.

Critério de aceite do Prompt Mestre para este incremento ("declare parcialmente bloqueado se o
PicoGK não puder ser executado") — **aplicado**: este incremento é entregue como parcialmente
bloqueado, não como concluído. Ver ADR-0007 e `ROADMAP.md` para os próximos passos de
desbloqueio.

## Resumo de bloqueios remanescentes antes da Fase 1

1. **`ARCH-DIVERGE-01`:** resolvido definitivamente pelo ADR-0002 (atualizado 2026-07-27):
   React + TypeScript + Vite (frontend) e FastAPI + PostgreSQL + Redis + MinIO (backend) são a
   arquitetura oficial, sem caráter provisório. O app PyQt5 existente é tratado como legado/
   referência histórica — poderá ser auditado e aproveitado se o código for disponibilizado, mas
   não bloqueia mais o desenvolvimento da arquitetura web.
2. Nenhum repositório de código foi localizado nesta sessão (nem nos uploads, nem no projeto de
   conhecimento "documentação doutorado"); o usuário confirmou explicitamente prosseguir do zero.
   A Fase 1 (fundação) foi iniciada sobre o scaffold v1, com o Incremento 1 (landing, login,
   dashboard, API de health/status, modelos iniciais) implementado nesta sessão — ver
   `IMPLEMENTATION_STATUS.md` para o que está realmente funcional, demonstrativo ou planejado.
