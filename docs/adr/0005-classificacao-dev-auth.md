# ADR-0005: Classificação da autenticação atual como DEV_AUTH

- Status: Aceita
- Data: 2026-07-27 (Incremento 1.1)
- Decisor: Adler Lima Botelho de Azevedo (usuário), correção de classificação solicitada

## Contexto

O relatório do Incremento 1 descreveu a autenticação (e-mail/senha com bcrypt, JWT stateless,
sessão em memória no frontend) sem deixar explícito o quão distante ela está da arquitetura de
identidade exigida pelo Prompt Mestre §9 para produção: OIDC/OAuth 2.1 com Authorization Code +
PKCE, MFA por TOTP e WebAuthn/passkeys, step-up authentication para ações sensíveis, painel de
sessões ativas, "break glass" auditado, entre outros. Isso corre o risco de a implementação
mínima ser confundida, em relatórios futuros, com uma solução pronta para uso clínico.

## Decisão

1. O modo de autenticação atual é nomeado explicitamente **`DEV_AUTH`** — constante em
   `apps/api/src/biomatcad_api/config.py` (`AUTH_MODE`), exposta publicamente via
   `GET /api/v1/system/status.auth_mode`, e mostrada no cartão de login do frontend.
2. `DEV_AUTH` é adequado a desenvolvimento e demonstração com dados sintéticos. **Nunca deve ser
   usado com dados clínicos reais**, independentemente do estado da suíte clínica (ADR-0004) —
   isso é uma limitação da camada de identidade, ortogonal ao estado operacional.
3. **Sem credenciais padrão silenciosas em produção**: `Settings.assert_secure_for_environment()`
   faz o processo recusar iniciar (`InsecureConfigurationError`) sempre que `ENVIRONMENT != test`
   e `API_SECRET_KEY` estiver ausente, vazio, igual ao valor padrão de desenvolvimento, ou mais
   curto que 32 caracteres. Chamado explicitamente em `create_app()`, portanto falha no processo
   de startup, não silenciosamente em tempo de requisição.
4. Auditoria: login (sucesso e falha), logout e tentativas de alteração da suíte clínica/estado
   independente (autorizadas, negadas por chave incorreta e negadas por falta de permissão) são
   todas registradas como `AuditEvent`.
5. `POST /api/v1/auth/logout` é **simbólico**: como o JWT é stateless e não há blocklist de
   tokens nesta fase, o token continua criptograficamente válido até expirar (30 min por
   padrão); o endpoint apenas registra o evento de auditoria e o frontend descarta o token em
   memória. Isso está documentado no docstring do endpoint e em `IMPLEMENTATION_STATUS.md` para
   que ninguém trate isso como revogação real de sessão.
6. Requisitos pendentes e rastreados (não implementados nesta fase), registrados em
   `REQUIREMENTS_MATRIX.md` sob `PM-ONLY-04`: OIDC/OAuth 2.1 + PKCE, MFA (TOTP/WebAuthn), step-up
   authentication, refresh token, blocklist/revogação real de sessão, painel de sessões ativas,
   RBAC/ABAC completo com os 17 perfis do Prompt Mestre §9, "break glass" com prazo e auditoria.

## Consequências

- Nenhum texto de status deste projeto (README, ARCHITECTURE.md, IMPLEMENTATION_STATUS.md,
  relatórios de incremento) deve descrever a autenticação atual como "pronta para produção
  clínica" ou equivalente — deve sempre ser referenciada como `DEV_AUTH`.
- Ambientes `local-network`/`staging`/`production` não conseguem sequer iniciar sem um
  `API_SECRET_KEY` real configurado — isso é testado (`tests/test_dev_auth_startup.py`).
- A migração de `DEV_AUTH` para a arquitetura OIDC completa é um incremento futuro de escopo
  significativo (serviço de identidade — Keycloak ou equivalente, `services/identity/` ainda
  vazio), não uma extensão incremental do código atual de `routers/auth.py`.
