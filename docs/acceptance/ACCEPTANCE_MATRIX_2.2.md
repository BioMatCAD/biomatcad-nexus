# Matriz de aceite final -- Incremento 2.2 Alpha Pesquisa

Branch: `incremento-2.2-alpha-pesquisa`. Commit-base desta rodada de fechamento: `922cbae`
(E2E completo do visualizador 3D já aprovado no Windows real, 15/15, exit code 0).
Commit final desta rodada de fechamento (antes do empacotamento): `d9138b7`.

Esta matriz cobre exclusivamente o que foi feito/reconciliado na rodada de fechamento (Fases
A-I). Para o histórico completo de todo o Incremento 2.2 (incluindo Voronoi, visualizador 3D,
observabilidade, GUI de pesquisa etc.), ver `REQUIREMENTS_MATRIX.md` seções G, H e I, e
`IMPLEMENTATION_STATUS.md`.

| Requisito | Evidência | Commit | Suíte executada | Ambiente | Resultado | Limitações | Status final |
|---|---|---|---|---|---|---|---|
| Reconciliação de pendências (Fase A) | `ROADMAP.md` seção "Reconciliação de pendências -- Fase A" | `b34d24c` | N/A (auditoria documental) | Sandbox | Todos os 11 itens classificados; nenhuma prova já aprovada foi repetida | Nenhuma | **Concluído** |
| `DesignAdvisor` concreto (Fase B) | `design_advisor_rule_based.py`; `test_design_advisor_rule_based.py` | `2486518` | pytest (33 testes dedicados) | Sandbox (Postgres real efêmero) | 33/33 passed; gap de cobertura fechado por mutation testing | Não é IA autônoma; nunca decisão clínica; sem RBAC dedicado (herda o da API) | **Concluído** |
| Segurança do ambiente de pesquisa, 14 itens (Fase C) | `test_security_hardening.py`; `docs/security/RESEARCH_SECURITY_POSTURE.md` | `61e3753` | pytest (12 testes dedicados + suíte completa) | Sandbox (Postgres real efêmero) | 12/12 passed; 1 gap real (CORS wildcard) corrigido e confirmado por mutation testing | Não é conformidade clínica/LGPD completa/segurança hospitalar/certificação regulatória; RBAC/ABAC completo (17 perfis) deliberadamente fora de escopo | **Concluído (dentro do escopo de pesquisa)** |
| Resiliência e recuperação de falha (Fase D) | `test_resilience_recovery.py`; alterações em `geometry_job_service.py`/`geometry_dispatcher.py` | `e4429e7` | pytest (21 testes novos/ajustados + suíte completa: 259 passed, 2 skipped) | Sandbox (Postgres real efêmero) | Todos passando; 4 correções de produção confirmadas por mutation testing manual | Launcher/instalador clínico completo permanece deliberadamente fora de escopo | **Concluído** |
| Triagem `npm audit`, 11 avisos (Fase E) | `docs/security/DEPENDENCY_AUDIT_2.2.md`; `package-lock.json` | `7469f88` | `npm audit`, `tsc`, `eslint`, `vitest` (128/128), `build`, `build:pages` | Sandbox | 4/11 corrigidos (patch, sem breaking change); 7/11 analisados individualmente e formalmente deferidos com mitigação documentada | 7 avisos remanescentes exigem migração major (Vitest 4, Vite 8, React Router 7) -- planejada, não urgente, fora deste incremento | **Concluído (triagem completa; correção parcial por decisão técnica documentada, não por omissão)** |
| Gates completos -- backend/frontend/worker/scripts (Fase F) | `ruff check`, `mypy`, `dotnet build/test`, PSParser | `f98a66e`, `93ffa27` | ruff, mypy, pytest (259 passed/2 skipped), tsc, eslint, vitest (128/128), build, build:pages, playwright --list (15 testes), dotnet build (0/0), dotnet test (111/111), PSParser (10/10) | Sandbox | Todos os gates aplicáveis executados e verificados; nenhum declarado aprovado sem execução real | Playwright real (execução completa, não apenas `--list`) e geração real de geometria via PicoGK continuam exigindo Windows -- já aprovados anteriormente, não repetidos | **Concluído** |
| Determinação de gate Windows complementar (Fase G) | `ROADMAP.md` seção "Fase G" | `a4f248b` | N/A (análise de evidência) | N/A | Nenhuma mudança desta rodada toca geometria/golden recipes/PicoGK/worker C#/UI nova | Reexecução do `Run-FinalGate.ps1` continua disponível como confirmação opcional | **Concluído -- nenhum gate obrigatório pendente** |
| Documentação científica e técnica final (Fase H) | `ARCHITECTURE.md`, `IMPLEMENTATION_STATUS.md`, `REQUIREMENTS_MATRIX.md`, `TEST_EVIDENCE.md`, `WORKER_STATUS.md`, `README.md` | `d9138b7` | N/A (revisão documental) | N/A | Todos os documentos principais atualizados e consistentes com o código/testes reais desta rodada | Nenhuma | **Concluído** |

## Verificação das condições de fechamento (Fase I)

| Condição | Verificado | Evidência |
|---|---|---|
| Nenhuma pendência obrigatória em aberto | Sim | Tabela acima; `ROADMAP.md` Fase A classificou todos os itens, nenhum "realmente pendente" ficou sem endereçamento nesta rodada |
| Todas as suítes aplicáveis estão verdes | Sim | Backend: 259 passed, 2 skipped, exit 0. Frontend: 128/128, build+build:pages OK. Worker: 111/111, build 0/0. Scripts: 10/10 sintaxe válida |
| Gates Windows obrigatórios aprovados | Sim | 4 gates já aprovados em rodadas anteriores (matriz Voronoi/Gyroid, hashes golden, E2E principal, E2E visualizador 15/15); Fase G confirmou que nenhum gate novo é necessário para as mudanças desta rodada |
| Vulnerabilidades corrigidas ou formalmente avaliadas/mitigadas | Sim | 4/11 corrigidas; 7/11 com análise individual de alcançabilidade e mitigação documentada (`DEPENDENCY_AUDIT_2.2.md`) |
| Documentação consistente | Sim | Fase H; nenhuma contradição encontrada entre ROADMAP/IMPLEMENTATION_STATUS/REQUIREMENTS_MATRIX/TEST_EVIDENCE/WORKER_STATUS/README |
| Árvore de trabalho limpa | Sim | `git status --porcelain` vazio, verificado nesta fase |
| `master` e as 3 tags protegidas intactos | Sim | `incremento-2.1-base`, `incremento-2.1.1-final`, `incremento-2.1.1-v2.2.1` com os mesmos SHAs de antes desta rodada; nenhum `master` local existe neste sandbox (característica estrutural já confirmada em rodadas anteriores, não uma alteração desta rodada) |
| Histórico linear | Sim | `git log --merges --oneline` vazio; 9 commits novos e lineares desde `922cbae` até `d9138b7` |

## Conclusão

Todas as condições de fechamento do Incremento 2.2 Alpha Pesquisa estão satisfeitas. O
incremento pode ser empacotado (Fase J).

**Escopo explicitamente fora deste incremento** (não avaliado nesta matriz, por não pertencer a
ele): launcher/instalador clínico completo, RBAC/ABAC completo com os 17 perfis do Prompt
Mestre, OIDC/MFA, FEM, DICOM, banco de dados científico populado, módulo farmacêutico
customizado, integração hospitalar, validação clínica, qualquer uso com dados reais de
pacientes. O sistema permanece exclusivamente de pesquisa.
