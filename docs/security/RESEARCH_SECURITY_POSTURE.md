# Postura de segurança do ambiente de pesquisa (Incremento 2.2, Fase C)

Este documento consolida, item a item, os 14 pontos de segurança pedidos explicitamente na
rodada de fechamento do Incremento 2.2 Alpha Pesquisa. Ele descreve o que existe e é testado
**hoje**, distinguindo sempre entre o que já era real antes desta rodada (com ou sem teste
dedicado) e o que foi corrigido/adicionado nesta Fase C.

**Não é uma declaração de conformidade clínica, LGPD plena, segurança hospitalar ou
certificação regulatória de qualquer tipo.** Este sistema permanece de pesquisa; RBAC/ABAC
completo com os 17 perfis institucionais, OIDC/OAuth 2.1 + PKCE, MFA/WebAuthn e step-up
authentication continuam `PM-ONLY-04e/f/g/h` -- deliberadamente fora de escopo, backlog de
fases futuras (ver `REQUIREMENTS_MATRIX.md`).

## 1. Autenticação e autorização

- **Autenticação**: classificada explicitamente como `AUTH_MODE="DEV_AUTH"` (e-mail/senha +
  JWT stateless) desde o Incremento 1.1 -- exposta em `GET /api/v1/system/status.auth_mode`,
  nunca apresentada como equivalente a OIDC/MFA (ADR-0005).
- **Autorização**: `require_admin` (role in {admin, superadmin}) protege toda ação
  administrativa (ativação de estados operacionais, suíte clínica). Não é RBAC/ABAC completo --
  é o mínimo coerente para pesquisa hoje.
- **Startup seguro**: `Settings.assert_secure_for_environment()` recusa iniciar fora de
  `ENVIRONMENT=test` se `API_SECRET_KEY` estiver ausente, for o valor padrão de
  desenvolvimento, ou tiver menos de 32 caracteres (`test_dev_auth_startup.py`, 5 testes).

## 2. Segregação por organização e projeto

Toda entidade (`Project`, `GeometryRecipe`, `Material`, `GeometryJob`, `Artifact`) carrega
`organization_id`, e cada rota consulta explicitamente via `_get_job_or_403`/equivalentes --
nunca por um filtro implícito. Testado em `test_geometry_job_security.py` (8 cenários:
projeto/receita/material de organizações cruzadas, IDs inexistentes, receita não validada) e
`test_artifact_download_is_denied_across_organizations`. Segregação por *projeto* dentro da
mesma organização segue o modelo de dados atual (recursos pertencem a um projeto de uma
organização) -- não há um segundo nível de RBAC por projeto além do vínculo direto ao
`organization_id` herdado.

## 3. Proteção de artefatos e downloads

- Download sempre autenticado via `Authorization: Bearer` (nunca token na URL) --
  `GET /artifacts/{id}/download`, `GET /jobs/{id}/manifest`.
- **Validação de caminhos (NOVO nesta rodada)**: `LocalStorageAdapter._resolve()` já
  resolvia a chave de armazenamento contra `base_dir` e rejeitava qualquer escape via `..`, mas
  não tinha NENHUM teste dedicado antes desta rodada. Adicionado
  `test_storage_adapter_rejeita_chave_com_path_traversal` (`test_security_hardening.py`) --
  prova que chaves como `../secret.txt`, `../../etc/passwd`, `sub/../../escape.bin` e um
  caminho absoluto (`/etc/passwd`) são todas rejeitadas com `ValueError`, para `put`/`get`/
  `exists`, e que nenhum arquivo é de fato escrito fora de `base_dir`.

## 4. Ausência de segredos hardcoded

Nenhum segredo real está commitado. `API_SECRET_KEY`/`operational_state_master_key` só têm
valores sintéticos/inseguros como *default* explícito de desenvolvimento, e o app recusa
iniciar com esses valores fora de `ENVIRONMENT=test` (item 1 acima). `.env.example` documenta
as variáveis sem valores reais.

## 5. Sanitização de logs

`RedactSensitiveFilter` (`logging_config.py`) já existia (Prompt Mestre §23.2: nunca logar
PHI/segredos), suprimindo a mensagem inteira quando contém qualquer uma das chaves sensíveis
(`password`, `senha`, `token`, `secret`, `authorization`, `master_key`, `cpf`, `rg`) --
mas também sem teste dedicado antes desta rodada. Adicionados
`test_redact_sensitive_filter_suprime_mensagens_com_chave_sensivel` (4 casos parametrizados:
senha, Bearer token, master key, CPF) e `test_redact_sensitive_filter_preserva_mensagens_sem_dado_sensivel`
(garante que o filtro não é agressivo demais e preserva logs operacionais normais).

## 6. Validação de caminhos

Ver item 3 (mesma defesa, `LocalStorageAdapter`).

## 7. Prevenção de command injection

`DotnetPicoGkWorkerClient.execute()` invoca o worker via `subprocess.Popen([...])` com uma
LISTA de argumentos (`[dotnet_bin, dll_path, job_json_path]`), nunca `shell=True`, e o conteúdo
da receita nunca chega à linha de comando -- é sempre gravado em `job.json` e lido pelo worker
como dado, nunca como comando. Isso já era verdade desde a implementação original, mas sem
teste dedicado. Adicionado
`test_worker_client_invoca_subprocesso_sem_shell_e_com_argumentos_em_lista`
(`test_security_hardening.py`): injeta metacaracteres de shell (`; rm -rf / #`, `` `id` ``,
`$(whoami)`) em campos da receita e confirma que (a) `subprocess.Popen` é chamado com uma
`list` e `shell` nunca `True`, (b) nenhum token da linha de comando contém o payload malicioso,
e (c) o payload só existe dentro do arquivo JSON gravado em disco, nunca interpretado como
comando.

## 8. Controle de upload/download

Não há upload de arquivo arbitrário pelo usuário nesta rodada (receitas são JSON estruturado
validado contra schema, nunca um arquivo binário enviado livremente). Download já coberto no
item 3.

## 9. Auditoria de ações relevantes

`AuditEvent` já registra `login_succeeded/failed`, `logout`,
`operational_state_activation_denied`, `admin_action_denied`,
`clinical_suite_activated/deactivated` e `artifact_downloaded` -- existente desde os
Incrementos 1.1/2.1, sem alteração nesta rodada.

## 10. Política explícita de dados sintéticos

Todo dado de demonstração/teste é sintético e rotulado como tal (seeds, golden recipes,
usuário E2E com senha sintética documentada). Nenhum arquivo deste repositório contém dado de
paciente real -- constatação estrutural (não uma alegação de processo formal de compliance):
não existe, em nenhum lugar do modelo de dados (`apps/api/src/biomatcad_api/models/`), campo
algum de identificação de paciente (nome, CPF, prontuário, data de nascimento). `Organization`,
`User`, `BioMatProject`, `GeometryRecipe`, `Material`, `GeometryJob`, `Artifact` descrevem
apenas entidades de pesquisa (organização, pesquisador, projeto, receita geométrica, material,
job de geometria, artefato gerado) -- não há onde um dado clínico real "vazaria" por engano,
porque a ausência do campo é a própria defesa.

## 11. Bloqueio de dados clínicos reais

Consequência direta do item 10: como não existe modelo de dado de paciente, não há vetor de
entrada para dado clínico real neste sistema. A suíte clínica (`CLINICAL_TEST` +
`CLINICAL_PILOT` + `CLINICAL_PRODUCTION`, Incremento 1.1) é uma feature-flag operacional que
controla VISIBILIDADE de funcionalidades no roadmap do produto -- não introduz, em código,
nenhuma via de entrada de dado de paciente real; permanece com o mesmo escopo desde o
Incremento 1.1 (ADR-0004), inalterado nesta rodada.

## 12. Comportamento seguro em falhas

`register_exception_handlers` (`errors.py`) já respondia com uma mensagem genérica
(`"Erro interno. Consulte os logs do servidor pelo identificador informado."`) e um `error_id`
de correlação para qualquer exceção não tratada, sem nunca expor a mensagem/tipo da exceção
Python real ao cliente -- existente desde o Incremento 2.1, sem teste dedicado antes desta
rodada. Adicionado `test_erro_nao_tratado_nunca_vaza_mensagem_interna_ao_cliente`: injeta uma
falha real (`RuntimeError` com uma string sensível fabricada) em uma dependência de rota e
confirma que a resposta HTTP 500 nunca contém a mensagem original nem o nome da classe da
exceção -- só o `error_id`/código genérico.

## 13. CORS e exposição de serviços

**Corrigido nesta rodada**: o comentário em `config.py` já dizia "CORS restritivo por padrão —
... nunca '*' fora de development", mas nenhum validador de fato IMPEDIA
`CORS_ALLOWED_ORIGINS=*` via variável de ambiente em `local-network`/`staging`/`production` --
era só uma convenção de código, não uma garantia. Adicionado `validate_cors_allowed_origins`
(mesmo padrão do já existente `validate_database_url`): falha alto e cedo no startup
(`ValueError`) se `"*"` aparecer em `cors_allowed_origins` fora de `development`/`test`.
Testado em `test_cors_rejeita_wildcard_fora_de_development_e_test`,
`test_cors_aceita_wildcard_em_development_e_test_apenas` e
`test_cors_aceita_lista_explicita_em_qualquer_ambiente`, com mutation testing confirmando que o
teste de rejeição genuinamente falha se o validador for desativado.

## 14. Permissões mínimas

Ações administrativas exigem `require_admin`; ações sobre a suíte clínica exigem, além disso, a
chave mestra operacional (`operational_state_master_key`) configurada explicitamente -- sem
essa chave, a suíte clínica nunca pode ser ativada, mesmo por um admin (`operational_state_service.py`).
Nenhuma rota concede permissão por padrão além do que o papel do usuário e a organização a que
pertence permitem.

## Resumo desta rodada (Fase C)

Dos 14 itens, 2 já tinham lacuna real de ENFORCEMENT (não apenas de teste): CORS `*` sem
validador (item 13, corrigido) -- os demais 13 itens já eram tecnicamente corretos por
construção, mas 4 deles (validação de caminhos, command injection, sanitização de logs,
comportamento seguro em falha) não tinham NENHUM teste de regressão dedicado antes desta
rodada. Todos os 5 pontos (1 correção de código + 4 lacunas de teste) foram fechados em
`apps/api/tests/test_security_hardening.py` (12 testes novos), com mutation testing aplicado
à correção de código (CORS).

RBAC/ABAC completo (17 perfis, OIDC, MFA, revogação de sessão), matriz regulatória formal
(Anvisa/ISO/IEC) e threat model STRIDE completo permanecem fora de escopo desta rodada --
`docs/regulatory/README.md` e `docs/threat-model/README.md` continuam como estrutura de
diretório para fases futuras, sem implementação (nenhuma mudança nesta rodada).
