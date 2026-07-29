# Cópia local do JSON Schema BioMatCEM

`geometry-recipe-v1.schema.json` neste diretório é uma CÓPIA de
`schemas/biomatcem/geometry-recipe-v1.schema.json` (raiz do monorepo), trazida para dentro de
`apps/web/src` para evitar depender de resolução de import cruzando a raiz do workspace pelo
bundler (Vite/TypeScript) em modo dev e no build estático do GitHub Pages.

Isto é uma cópia FÍSICA de arquivo, não um symlink nem um import direto do arquivo canônico —
para evitar que as duas cópias divirjam silenciosamente, `tests/schemaSync.test.ts` compara
byte a byte (via JSON.parse + comparação profunda) esta cópia contra o arquivo canônico a cada
execução da suíte de testes do frontend. Se alguém editar apenas uma das duas cópias, o teste
falha imediatamente.

Nunca edite este arquivo diretamente -- edite `schemas/biomatcem/geometry-recipe-v1.schema.json`
e rode `npm test --workspace apps/web` para copiar/verificar.
