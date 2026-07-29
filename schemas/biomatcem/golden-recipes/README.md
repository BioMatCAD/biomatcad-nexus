# Golden recipes — BioMatCEM (Incremento 2.1)

Três receitas pequenas, versionadas e sintéticas, usadas como fixtures de teste (validação de
schema, criação de job, determinismo do contrato). Nenhuma contém dados clínicos.

| Arquivo | Domínio | Modo | Propósito |
|---|---|---|---|
| `block-gyroid-v1.json` | bloco 10×10×10mm | final | caso principal, domínio retangular |
| `cylinder-gyroid-v1.json` | cilindro r=5mm h=12mm | final | caso principal, domínio cilíndrico |
| `preview-gyroid-low-res-v1.json` | bloco 5×5×5mm | preview | resolução reduzida, iteração rápida |

Os campos `_golden_recipe_id` e `_description` são metadados do repositório de testes, não
fazem parte do schema `geometry-recipe-v1` (são removidos antes da validação — ver
`tests/conftest.py::load_golden_recipe`).

**Status de execução real (worker C#/PicoGK):** bloqueado neste ambiente — ver
`apps/geometry-worker/WORKER_STATUS.md`. Estas receitas foram validadas contra o JSON Schema e
usadas para testar a criação/enfileiramento de jobs e a falha controlada do worker; a geometria
real (STL determinístico gerado a partir delas) não pôde ser gerada nem verificada nesta sessão.
