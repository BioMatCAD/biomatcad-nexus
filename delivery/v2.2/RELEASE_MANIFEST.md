# Manifesto de entrega -- Incremento 2.2 Alpha Pesquisa (fechamento final)

- **Branch:** `incremento-2.2-alpha-pesquisa`
- **Commit-base desta rodada de fechamento:** `922cbae`
- **Tag final desta entrega:** `incremento-2.2-alpha-pesquisa-final`
- **Escopo:** pesquisa apenas. Sem dados clínicos reais. Sem diagnóstico ou decisão de
  tratamento. Launcher/instalador clínico completo deliberadamente fora de escopo.

## Conteúdo do pacote

| Arquivo | Descrição |
|---|---|
| `biomatcad-nexus-v2.2-source.zip` | Snapshot do código-fonte na tag `incremento-2.2-alpha-pesquisa-final` (via `git archive`), sem histórico. |
| `biomatcad-nexus-v2.2-final.bundle` | Bundle Git completo (`git bundle --all`) -- todo o histórico, todas as tags protegidas, a branch `incremento-2.2-alpha-pesquisa`. |
| `SHA256SUMS.txt` | Checksums SHA-256 dos dois arquivos acima. |
| `delivery/v2.2/RELEASE_MANIFEST.md` | Este arquivo. |
| `delivery/v2.2/ACCEPTANCE_MATRIX.md` | Matriz de aceite final (requisito/evidência/commit/suíte/ambiente/resultado/limitações/status). |
| `delivery/v2.2/WINDOWS_RESEARCH_QUICKSTART.md` | Guia rápido de execução no Windows. |
| `delivery/v2.2/TEST_EVIDENCE_v2.2_FINAL_REPORT.md` | Relatório executivo consolidado de todos os testes desta rodada. |

## O que está excluído do pacote de origem (`biomatcad-nexus-v2.2-source.zip`)

O `git archive` só inclui arquivos rastreados pelo Git; o `.gitignore` do repositório já garante
que os seguintes itens nunca são versionados e, portanto, nunca aparecem no pacote:

- `node_modules/`, `.venv/`, `venv/`, `bin/`, `obj/` (dependências e artefatos de build)
- `dist/`, `build/`, `*.egg-info/` (saídas de build)
- `.env`, `.env.*.local`, `*.pem`, `*.key` (segredos)
- `data/patients/`, `data/phi/`, `*.dcm.real` (dados clínicos/sensíveis -- nunca existiram neste
  repositório)
- `apps/api/data/` (armazenamento local transitório de artefatos gerados ao rodar a API)
- `*.db` (bancos de dados locais de teste/desenvolvimento, exceto fixtures versionadas em `docs/`)
- Logs (`*.log`, exceto os `EVIDENCE_*.log` do worker, que são evidência histórica intencional)
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `coverage/`, `htmlcov/`
- `test-results/`, `playwright-report/`, `blob-report/` (resultados transitórios de execução)

Confirmado nesta rodada (Fase J) via `git ls-files | grep -E "node_modules/|\.venv/|/bin/|/obj/"`
(0 ocorrências) e busca por `.env`/`.pem`/`.key`/`patients`/`phi`/`*.db` rastreados (0
ocorrências).

## Verificação de integridade

```powershell
# Após baixar o pacote:
Get-FileHash biomatcad-nexus-v2.2-source.zip -Algorithm SHA256
Get-FileHash biomatcad-nexus-v2.2-final.bundle -Algorithm SHA256
# Comparar com SHA256SUMS.txt
```

```bash
# Linux/macOS:
sha256sum -c SHA256SUMS.txt
```

## Restauração e verificação (executada nesta rodada, ver seção correspondente do relatório de
## fechamento)

O bundle foi restaurado em um diretório limpo separado, com `HEAD`, a tag
`incremento-2.2-alpha-pesquisa-final`, as 3 tags protegidas anteriores, e o histórico linear
(sem merges) todos confirmados antes da entrega -- ver `docs/acceptance/ACCEPTANCE_MATRIX_2.2.md`
e o log desta sessão.

## Escopo explicitamente fora deste incremento

Launcher/instalador clínico completo, RBAC/ABAC completo (17 perfis do Prompt Mestre), OIDC/
OAuth2.1+PKCE, MFA/WebAuthn, FEM, DICOM, banco de dados científico populado, módulo farmacêutico
customizado, integração hospitalar, validação clínica, qualquer uso com dados reais de
pacientes. Nenhum destes itens é declarado concluído ou parcialmente concluído por este pacote.

## Aviso de pesquisa

Este sistema é exclusivamente uma ferramenta de pesquisa em desenvolvimento. Nenhuma saída deste
sistema (geometria, métricas, recomendações do `DesignAdvisor`, ou qualquer outro artefato) deve
ser usada para diagnóstico, decisão de tratamento, ou qualquer aplicação clínica real. O
`DesignAdvisor` explicitamente nunca produz uma decisão clínica -- apenas recomendações
metodológicas rastreáveis com aviso fixo de ausência de validação clínica.
