# ADR-0006: Schema versionado e validação estrita da receita BioMatCEM

- Status: Aceita
- Data: 2026-07-29 (Incremento 2.1)
- Decisor: Adler Lima Botelho de Azevedo (usuário), especificado no Prompt Mestre e na
  descrição detalhada do Incremento 2.1

## Contexto

O Incremento 2.1 exige que o navegador nunca envie código C#, Python ou expressão arbitrária ao
backend/worker — apenas parâmetros de uma receita geométrica declarativa ("BioMatCEM"). É
necessário um contrato único, versionado, validável tanto no frontend quanto no backend, que
rejeite campos desconhecidos (para impedir injeção de comportamento não previsto) e que permita
evolução futura sem quebrar receitas já persistidas.

## Decisão

1. **JSON Schema Draft 2020-12** em `schemas/biomatcem/geometry-recipe-v1.schema.json`, com
   `"additionalProperties": false` em **todos** os níveis do documento (raiz, `domain`,
   `topology`, `resolution`, `compute_limits`) — qualquer campo não previsto é rejeitado, não
   ignorado silenciosamente.
2. `schema_version` é um campo obrigatório com valor `const "1.0.0"` nesta versão. Uma mudança
   incompatível de schema exigirá um novo arquivo (`geometry-recipe-v2.schema.json`) e um novo
   valor de `schema_version` — nunca uma alteração retroativa do schema v1 que invalidaria
   receitas já persistidas com checksum calculado sobre o v1.
3. Apenas topologia `gyroid` e domínios `block`/`cylinder` são aceitos nesta versão — os demais
   (TPMS adicionais, malhas importadas) ficam para incrementos futuros, dentro do mesmo arquivo
   de schema versionado.
4. **Validação em duas camadas, nunca uma só**:
   - Backend: `services/recipe_service.py` usa `jsonschema.Draft202012Validator` como fonte de
     verdade — é o único lugar que decide se uma receita é persistida.
   - Frontend: `recipeValidationOffline.ts` reimplementa as mesmas regras em JS puro, usada
     apenas no modo demo (GitHub Pages, sem backend) e como validação otimista antes do envio
     no modo real — nunca substitui a validação do backend, que roda de novo em
     `POST /recipes/validate` e em `POST /projects/{id}/recipes`.
5. **Canonicalização + checksum**: toda receita validada é serializada em forma canônica (chaves
   ordenadas, separadores compactos) e recebe um `checksum_sha256` real (backend) — o
   `fingerprint()` FNV-1a do modo demo é explicitamente não-criptográfico e nunca comparado
   contra o checksum real, para não criar uma falsa sensação de paridade de segurança entre os
   dois clientes.
6. Clonar uma receita (`POST /recipes/{id}/clone`) sempre incrementa `version` e nunca modifica
   o corpo canônico da receita original — testado explicitamente
   (`test_materials_projects_recipes_api.py`).

## Consequências

- Nenhum código arbitrário pode chegar ao worker C#: o worker só recebe o JSON já validado e
  canonicalizado pelo backend (`JobEnvelope.cs` desserializa exatamente os campos do schema,
  sem `eval`/reflexão dinâmica sobre entrada do usuário).
- Evoluir o schema (ex.: adicionar uma topologia TPMS nova) exigirá um novo arquivo versionado,
  não uma edição in-place — mais arquivos ao longo do tempo, mas nenhuma receita antiga se torna
  inválida silenciosamente.
- Duplicar a validação em dois lugares (Python real + JS offline) cria risco de divergência
  entre as duas implementações; mitigado por testes dedicados (`test_recipe_schema.py`)
  cobrindo os mesmos casos de borda nos dois lados, mas não há uma garantia formal de
  equivalência total — um teste de propriedade (property-based) comparando as duas
  implementações é um item de backlog razoável para o próximo incremento.
