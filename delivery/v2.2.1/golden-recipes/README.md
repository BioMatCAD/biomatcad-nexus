# Golden recipes — BioMatCEM (Incremento 2.1.1)

Três receitas pequenas e versionadas, usadas como fixtures de teste (validação de schema, criação
de job, execução real do worker). Nenhuma contém dados clínicos.

Desde o Incremento 2.1.1, cada arquivo `*.json` abaixo é um corpo JSON **diretamente válido**
contra `../geometry-recipe-v1.schema.json` — sem nenhum campo de metadado misturado no corpo e sem
nenhuma função de teste removendo campos antes da validação. Isso é verificado diretamente por
`apps/api/tests/test_recipe_schema.py` (Draft202012Validator sobre o arquivo bruto).

Metadados descritivos (id legível, descrição) ficam separados em `METADATA.json`, que não é
validado contra o schema de receita e não é lido pelo worker.

| Arquivo | Domínio | Modo | wall_thickness_mm | target_porosity_pct | Propósito |
|---|---|---|---|---|---|
| `block-gyroid-v1.json` | bloco 10×10×10mm | final | 0.6mm (cell 2.0mm) | 60% | caso principal, domínio retangular |
| `cylinder-gyroid-v1.json` | cilindro r=5mm h=12mm | final | 0.45mm (cell 1.5mm) | 55% | caso principal, domínio cilíndrico, valida corte booleano real pelo volume do cilindro |
| `preview-gyroid-low-res-v1.json` | bloco 5×5×5mm | preview | 0.75mm (cell 2.5mm) | 60% | resolução reduzida, valida diferença real preview vs. final |

**Status de execução real (worker C#/PicoGK):** o worker não pode ser executado neste ambiente de
desenvolvimento (sandbox Linux, sem runtime nativo PicoGK linux-x64 — ver
`apps/geometry-worker/WORKER_STATUS.md` e ADR-0007). O código do worker foi corrigido no
Incremento 2.1.1 (domínio cilíndrico real, interseção booleana, espessura/isovalor, calibração de
porosidade, determinismo por seed) e compila/passa testes unitários independentes de PicoGK, mas a
execução real destas três receitas (geração do STL, verificação de determinismo, watertight,
métricas) depende de execução em Windows x64 pelo usuário — ver
`docs/examples/WINDOWS_EXECUTION_KIT.md`. Enquanto esse retorno não ocorre, o item de aceite
"worker PicoGK executado realmente" permanece **pendente**, não concluído.
