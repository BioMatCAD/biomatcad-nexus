# OpenAPI — snapshot do Incremento 2.1 (reverificado no Incremento 2.1.1)

`openapi-v2.2-snapshot.json` é um snapshot gerado via `app.openapi()` (FastAPI), com os 28
endpoints reais expostos (health/ready/version, auth, estado operacional, materiais, projetos,
receitas, jobs, artefatos). Não é gerado automaticamente em CI — para obter a versão sempre
atualizada, rode a API e acesse `GET /api/v1/openapi.json` (ou a UI interativa em
`/api/v1/docs`).

**Reverificação no Incremento 2.1.1**: as correções deste incremento (autorização entre
organizações, fila com claim atômico, cancelamento real, manifesto reestruturado, `reason_code`
estruturado nos erros) alteram comportamento e corpos de erro em runtime, mas **não** alteram a
forma estática do schema OpenAPI — os corpos de erro usam o mesmo modelo genérico já existente
(`{"error": {"id", "code", "message", "details"}}`, com `details` sendo um objeto livre que
agora também pode carregar `reason_code`), e a receita BioMatCEM continua sendo validada como um
blob JSON contra o JSON Schema separado (`schemas/biomatcem/geometry-recipe-v1.schema.json`),
não como campos individuais tipados no OpenAPI. Para confirmar isso nesta sessão, o schema foi
regerado ao vivo (`create_app().openapi()`, sem depender de banco de dados — `ENVIRONMENT=test`
é suficiente) e comparado byte a byte (após normalização de ordenação de chaves) com o arquivo
deste diretório: **idêntico, nenhuma divergência encontrada**. Ou seja, o snapshot já refletia
corretamente a API mesmo após todas as correções do Incremento 2.1.1 — não foi necessário
regravar o arquivo.

`packages/contracts` (geração de tipos TypeScript a partir deste OpenAPI) permanece backlog —
ver `REQUIREMENTS_MATRIX.md`; os tipos do frontend (`apps/web/src/api/types.ts`) ainda são
mantidos manualmente, espelhando `apps/api/src/biomatcad_api/schemas/*.py`.
