# Roadmap — BioMatCAD Nexus

Este roadmap reflete o estado real após o Incremento 2.1 (Fase 2, entregue parcialmente
bloqueado) e o Incremento 2.1.1 (corretivo sobre defeitos da auditoria do 2.1, também entregue
parcialmente bloqueado no mesmo ponto — ver `IMPLEMENTATION_STATUS.md`, ADR-0007 e ADR-0008).
Não é uma promessa de prazos; é uma priorização técnica, atualizada a cada incremento aceito.
Ver `REQUIREMENTS_MATRIX.md` para o mapeamento completo de requisitos e `docs/adr/` para as
decisões que o sustentam. Atualizado em 2026-08-06 com a rodada Voronoi do
Incremento 2.2 (segunda topologia real, `voronoi_cell_edges_v1`) — ver seção dedicada abaixo.

## Feito

- **Fase 1 (Incrementos 1 e 1.1)**: fundação executável — auth `DEV_AUTH`, estado operacional
  (Pesquisa/Laboratório/suíte clínica), modelos iniciais, frontend com landing/login/dashboard,
  histórico Git preservado em bundle.
- **Fase 2 (Incremento 2.1)**: primeira vertical funcional do núcleo BioMatCAD — material
  documentado → projeto → receita BioMatCEM → job geométrico → worker C#/PicoGK → scaffold
  Gyroid → métricas → artefatos → visualização 3D. **Parcialmente bloqueado**: o worker
  compila e tem seu contrato testado, mas a execução real do PicoGK está bloqueada neste
  sandbox (ausência de runtime nativo linux-x64 no pacote oficial 2.2.0 — ver ADR-0007).
- **Fase 2 (Incremento 2.1.1, corretivo)**: corrigidos defeitos encontrados em auditoria do
  2.1 — semântica espessura/isovalor do schema (ADR-0008), domínio cilíndrico recortado pelo
  volume real via SDF (não bounding box), espessura/isovalor/porosidade/seed efetivamente
  aplicados, solda de vértices na malha (corrigindo a divergência STL-vs-manifesto encontrada na
  auditoria), autorização real entre organizações antes de criar um `DesignRun`, fila com claim
  atômico (`SELECT ... FOR UPDATE SKIP LOCKED`, provado sem duplicidade em 24 jobs concorrentes
  reais), cancelamento real com kill de árvore de processos e proteção de corrida, manifesto
  reestruturado com SHA-256 fora do próprio JSON, validação de receita no frontend migrada para
  Ajv contra o schema real, fingerprint de demonstração corrigido. **Mesmo bloqueio de execução
  real do PicoGK** desta sessão continua valendo — nenhuma dessas correções foi provada contra
  uma malha PicoGK real ainda (ver `IMPLEMENTATION_STATUS.md`).
- **Fase 2 (Incremento 2.2 Alpha Pesquisa, em andamento)**: observabilidade real integrada à
  GUI; GUI completa de pesquisa (retry, seleção de material, aviso de proveniência); contrato
  `TopologyProvider` versionado (Gyroid real, Voronoi registrado como `planned`, ADR-0009);
  documentação de preparação técnica para Voronoi (sem código); módulo de inteligência
  computacional (apenas contratos + registro de decisão manual, sem IA autônoma real);
  identidade visual oficial integrada (logo, favicon, PWA, página Sobre); visualizador 3D
  consolidado com STL real (checklist completo de recursos, carregamento seguro com checksum,
  controles de visualização, métricas/proveniência, limites de desempenho e descarte de
  recursos WebGL, suíte de testes de componente e correção de 4 bugs reais encontrados durante
  a auditoria/testes -- ver `docs/architecture/viewer-3d-audit.md` e a seção dedicada em
  `IMPLEMENTATION_STATUS.md`). Launcher Windows permanece formalmente **deferido** (não
  retomado).
- **Fase 2 (Incremento 2.2, rodada Voronoi)**: segunda topologia real implementada
  (`voronoi_cell_edges_v1`) -- sítios determinísticos por seed, tesselação Voronoi 3D real via
  `MIConvexHull` (não Delaunay renomeado), grafo de arestas recortado pelo domínio via SDF real,
  struts implícitos com suavização de nós, calibração de porosidade sobre malha real, métricas
  específicas completas, `VoronoiTopologyProvider` registrado (`status="implemented"`, sem
  regressão no Gyroid), 3 golden recipes, frontend completo (editor, estimativa de custo, aviso
  de receita pesada, demo honesto sem fabricar sucesso), auditoria STL independente escrita do
  zero, caderno de invenção confidencial, roteiro único de validação Windows -- ver
  `IMPLEMENTATION_STATUS.md` (seção "Rodada Voronoi") e `TEST_EVIDENCE.md` (seção 19). **Ainda
  não concluído**: nenhuma execução real do PicoGK sobre as golden recipes Voronoi foi
  confirmada nesta rodada (depende de execução Windows pelo usuário); empacotamento final v2.2
  continua não feito.

## Próximo (prioridade, nesta ordem)

1. **Executar o worker geométrico de verdade no Windows do usuário** e devolver os resultados
   para fechar os itens de aceite que dependem disso — guia completo em
   `docs/examples/WINDOWS_EXECUTION_KIT.md`. Sem isso, a Fase 3 não deve começar (condição
   explícita do Prompt Mestre). O que precisa ser confirmado com uma execução real (não apenas
   testes unitários matemáticos, já feitos no Incremento 2.1.1):
   - Geração real de um scaffold Gyroid via `Voxels`/`Mesh` do PicoGK, com o domínio cilíndrico
     de fato recortado pelo volume real (não a bounding box).
   - Espessura/isovalor/porosidade/seed efetivamente refletidos na malha resultante.
   - Diferença real preview vs. final (voxel size efetivo).
   - Determinismo geométrico real: mesma receita + mesma seed, em duas execuções, produz o
     mesmo SHA-256 de STL.
   - Métricas (`GeometryMetricsCalculator`) e manifesto coerentes com o STL real gerado (hoje
     só provados contra malhas sintéticas de teste).
   - E2E Playwright (`apps/web/e2e/`) executado de ponta a ponta — bloqueado neste sandbox
     Linux (falta `libXdamage.so.1`/dependências nativas do Chromium, `sudo` desabilitado).
   - Alternativa não tentada: investigar um build nativo do PicoGK a partir do código-fonte C++
     para linux-x64 — caminho mais lento, exige avaliação de licença/suporte antes de adotar.
2. **Carregar dados reais de materiais** (AP-07: 32+ materiais, 43+ referências DOI) no catálogo
   que hoje está vazio — sem inventar nenhum valor, só o que estiver expressamente nos
   documentos-fonte auditados (`docs/SOURCE_DOCUMENTS.md`) ou claramente rotulado como
   sintético.
3. **RBAC básico por organização/projeto** (`PM-ONLY-04h`) — hoje só existe `role` de string
   simples; falta hierarquia institucional real antes de abrir o sistema a múltiplas
   organizações de verdade.
4. **Segunda topologia TPMS** (Schwarz-P ou IWP) como `schema_version "1.1.0"` do BioMatCEM,
   seguindo o padrão de versionamento do ADR-0006 — só depois do worker desbloqueado, para não
   acumular funcionalidade não verificável.
5. **FEM (Fase 2, continuação)** — explicitamente fora de escopo do Incremento 2.1/2.1.1; só
   deve começar depois que a vertical geométrica estiver realmente executável.

## Pendências para fechar o Incremento 2.2 Alpha Pesquisa

Registradas aqui para não perder o fio entre sessões — nenhuma delas foi decidida como "próxima"
sem confirmação do usuário, apenas listadas como o que falta para poder declarar este
incremento concluído:

1. ~~**Visualizador 3D consolidado**~~ -- **CONCLUÍDO nesta rodada** (branch
   `incremento-2.2-alpha-pesquisa`, commits `32f4969`..`4180a67`): STL real (binário e ASCII),
   download autenticado com checksum e limite de tamanho, todos os controles do checklist
   (órbita/pan/zoom, wireframe, transparência/opacidade, eixos, grade, bounding box, clipping,
   screenshot, fullscreen), painel de proveniência com detecção de divergência API-vs-manifesto,
   cancelamento, descarte completo de recursos WebGL, fallback sem WebGL. Voronoi real
   continua deliberadamente fora desta rodada (item 2 abaixo). Pendência remanescente, não
   escondida: E2E Playwright em navegador real dos novos controles ainda não executado (mesmo
   bloqueio de sandbox de sempre — ver `docs/architecture/viewer-3d-audit.md`).
2. ~~**`VoronoiTopologyProvider` real**~~ -- **CONCLUÍDO na rodada Voronoi** (commits
   `e07a5e2`..`bf756a4`): geração de sítios, tesselação 3D real (`MIConvexHull`, MIT, licença
   auditada), grafo, struts, suavização de nós, calibração de porosidade, métricas, golden
   recipes, frontend, auditoria STL independente e roteiro Windows -- todos implementados e
   testados. Pendência remanescente, não escondida: nenhuma execução real do PicoGK sobre as
   golden recipes Voronoi foi confirmada neste sandbox -- ver
   `scripts/Run-VoronoiWindowsValidation.ps1` (pronto, nunca executado) e a lista "O que ainda
   depende de execução Windows real" em `IMPLEMENTATION_STATUS.md`.
3. **`DesignAdvisor` concreto** — hoje é só um `Protocol` sem implementação; qualquer
   implementação futura precisa registrar-se explicitamente (mesmo princípio de
   não-descoberta-automática do `TopologyProviderRegistry`) e nunca decidir sozinha sem revisão
   humana registrada.
4. **Empacotamento final v2.2** — explicitamente NÃO feito nesta rodada, por instrução: nenhum
   pacote final foi gerado, e o incremento não foi declarado concluído.

## Dependências deferidas (Incremento 2.1.1)

17 vulnerabilidades npm de **tooling de desenvolvimento apenas** (ESLint 8.x e sua cadeia —
`@eslint/eslintrc`, `minimatch`, `brace-expansion`, etc. —, e Vite/Vitest/esbuild) foram
deliberadamente **não** corrigidas nesta sessão, por decisão explícita do usuário contra
atualizações forçadas/indiscriminadas — cada uma tem risco de breaking change real (majors:
ESLint 9/10 com flat config, Vite 8/Vitest 4) e explorabilidade nula ou muito baixa no artefato
de produção entregue (`dist/`), conforme análise item a item em
`docs/security/DEPENDENCY_AUDIT_2.1.1.md`. Migração planejada, não urgente:

- Migrar ESLint para flat config (`eslint.config.js`) e atualizar para 9.x/10.x.
- Avaliar migração de Vite 5→8 e Vitest→4 (ambos majors, múltiplas mudanças de API/config).
- **Migração para React Router v7** — o bump não-quebrador já aplicado neste incremento
  (6.26.2→6.30.4) resolve a maior parte do risco prático, mas o advisory de segurança
  (GHSA-jjmj-jmhj-qwj2) ainda afeta toda a série 6.x; a correção completa exige a migração major
  para v7 (API de rotas mudou, `createBrowserRouter`/tipos), avaliada e feita como item dedicado,
  não misturada a outra tarefa.

## Mais adiante (fora de escopo dos próximos incrementos)

- DICOM/imagens médicas, LIMS/ELN/terapia celular, prontuário/telemedicina/agenda clínica —
  `PM-ONLY-01/02/03` — todos fora de escopo até o núcleo científico (CAD/FEM/materiais/ML)
  estar consolidado, por decisão de sequenciamento, não por reavaliação do escopo confirmado em
  ADR-0001/ADR-0003.
- Matriz regulatória completa (`PM-ONLY-05`) — depende dos módulos clínicos acima existirem
  primeiro.
- OIDC/OAuth2.1+PKCE, MFA/WebAuthn, step-up authentication (`PM-ONLY-04e/04f/04g`) — substituir
  `DEV_AUTH` antes de qualquer uso com dados reais (nunca clínicos, mesmo depois).

## Princípio de sequenciamento

Nenhum incremento futuro deve ser apresentado como mais completo do que realmente é. Se um
bloqueio de ambiente (como o do PicoGK neste incremento) se repetir, o padrão a seguir é o
mesmo: implementar o máximo do contrato possível, testar genuinamente o que não depende do
bloqueio, documentar a evidência do bloqueio, e declarar o incremento parcialmente bloqueado —
nunca simular sucesso.
