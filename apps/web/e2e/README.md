# E2E (Playwright) — Incremento 2.1.1, item 12

Este diretório contém um teste E2E real (não simulado) do caminho:
login → materiais → projeto → receita → design-run → status do job → visualização/download.

## Status neste ambiente de desenvolvimento: BLOQUEADO

Tentei instalar e executar o Playwright de verdade neste sandbox Linux:

```
npx playwright install chromium   # download dos binários teve sucesso
node -e "require('@playwright/test').chromium.launch()"
```

Resultado real (não simulado):

```
[pid=19][err] .../chrome-headless-shell: error while loading shared libraries:
libXdamage.so.1: cannot open shared object file: No such file or directory
```

`npx playwright install --with-deps chromium` (que instalaria as bibliotecas de sistema
faltantes via apt) falha porque este sandbox não tem acesso a `sudo`/root:

```
sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
```

Este é o MESMO tipo de bloqueio documentado para o worker PicoGK (ambiente sem os
privilégios/dependências nativas necessários, sem contorno silencioso possível) -- ver
`apps/geometry-worker/WORKER_STATUS.md`. Não fabriquei um resultado de execução: o teste abaixo
nunca rodou até o fim neste ambiente.

## Re-confirmação real (2026-07-29, Incremento 2.1.1, pós-correção de calibração)

Reexecutei a tentativa de verdade neste mesmo sandbox, para o item 10 do pedido do usuário
("avançar para validação de interface integrada e E2E Playwright"). Resultado, também real e
não fabricado:

- `chromium_headless_shell` (já baixado de uma tentativa anterior): falha idêntica,
  `libXdamage.so.1: cannot open shared object file: No such file or directory`.
- Tentei também o motor **Firefox** (`npx playwright install firefox` + `firefox.launch()`),
  para verificar se um motor diferente escaparia da mesma classe de dependência nativa ausente:
  falhou pelo mesmo motivo -- o próprio Playwright detecta a falta de dependências do host antes
  de lançar (`Host system is missing dependencies to run browsers`), listando `libxdamage1` e
  `libgtk-3-0` como pacotes necessários.
- Tentei baixar o `.deb` de `libxdamage1` diretamente via `apt-get download` (que não exige
  root, apenas rede) para extrair a biblioteca localmente sem precisar de `sudo` -- isso também
  falhou, mas por um motivo diferente e mais fundamental: o próprio acesso de rede a
  `archive.ubuntu.com` está bloqueado neste sandbox (`502 Bad Gateway`), não apenas a instalação
  privilegiada.

Conclusão honesta: o bloqueio é duplo e não contornável dentro deste ambiente -- falta tanto a
biblioteca nativa quanto qualquer caminho de rede ou privilégio para obtê-la. Nenhum resultado
de E2E foi ou será fabricado neste sandbox. A execução real do E2E, assim como a do worker
PicoGK, depende do usuário rodar os comandos abaixo no seu próprio Windows.

## Como executar (Windows, onde o worker também será testado)

```powershell
cd apps/web
npm install
npx playwright install --with-deps chromium
# Backend real rodando em outro terminal (uvicorn) + dispatcher, apontando para um Postgres real
$env:E2E_API_BASE_URL = "http://localhost:8000"
$env:E2E_WEB_BASE_URL = "http://localhost:5173"
npm run test:e2e
```

O `globalSetup` (`e2e/global-setup.ts`) chama um script Python auxiliar
(`apps/api/scripts/seed_e2e_user.py`) para criar um usuário/organização de teste diretamente no
banco -- não há endpoint público de registro nesta versão da API (autenticação é apenas login,
ver `routers/auth.py`).

## O que este E2E cobre e o que NÃO cobre

Cobre com o backend e frontend REAIS: autenticação, CRUD de materiais/projetos/receitas,
criação de design-run, transição de status via um job efetivamente despachado. Para o job
chegar a `succeeded` sem depender do PicoGK (que é o próprio objeto do bloqueio parcial deste
incremento), o script de setup despacha o job de teste com o mesmo `FakeWorkerClient` rotulado
usado nos testes de integração Python (`apps/api/tests/test_geometry_job_orchestration.py`) --
isto é explicitado no próprio teste E2E e NUNCA deve ser confundido com geometria real do
PicoGK. A geometria real do PicoGK continua sendo validada separadamente (worker C#,
`apps/geometry-worker/tests/`) e via execução manual no Windows.
