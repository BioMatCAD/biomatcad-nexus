# OpenAPI — snapshot do Incremento 2.1

`openapi-v2.2-snapshot.json` é um snapshot gerado nesta sessão via `app.openapi()`
(FastAPI), com os 28 endpoints reais expostos após o Incremento 2.1 (health/ready/version,
auth, estado operacional, materiais, projetos, receitas, jobs, artefatos). Não é gerado
automaticamente em CI — para obter a versão sempre atualizada, rode a API e acesse
`GET /api/v1/openapi.json` (ou a UI interativa em `/api/v1/docs`).

`packages/contracts` (geração de tipos TypeScript a partir deste OpenAPI) permanece backlog —
ver `REQUIREMENTS_MATRIX.md`; os tipos do frontend (`apps/web/src/api/types.ts`) ainda são
mantidos manualmente, espelhando `apps/api/src/biomatcad_api/schemas/*.py`.
