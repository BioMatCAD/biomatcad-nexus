# ADR-0002: Stack tecnológica da fundação (Fase 1)

- Status: Aceita (provisória — sujeita a revisão quando o app PyQt5 existente for auditado)
- Data: 2026-07-27
- Decisor: Adler Lima Botelho de Azevedo (usuário), com recomendação técnica desta sessão

## Contexto

O usuário confirmou que nenhum repositório de código existente será conectado a esta sessão
("comece do zero"). Isso significa que a recomendação do Prompt Mestre §6.1 de auditar um app
PyQt5 pré-existente antes de decidir entre mantê-lo, migrá-lo ou empacotá-lo **não pôde ser
executada nesta sessão** — não porque a decisão foi tomada, mas porque não havia código
disponível para auditar. O `memory.md` do usuário registra a existência de um app PyQt5 real de
8 módulos, mas seu código-fonte não foi fornecido.

A Tese (§2) propõe explicitamente "arquitetura modular cliente-servidor, com backend em Python
e frontend web-based em React.js" — essa é a única arquitetura-alvo com respaldo documental.

## Decisão

1. A fundação da Fase 1 usa a arquitetura descrita na Tese §2 e detalhada no Prompt Mestre §6:
   monorepo com `apps/web` (React + TypeScript + Vite), `apps/api` (FastAPI + Pydantic +
   SQLAlchemy/Alembic), `apps/geometry-worker` (C#/.NET + PicoGK/ShapeKernel),
   `apps/compute-worker` (Python científico), PostgreSQL como banco principal.
2. **Este ADR não decide** se o app PyQt5 existente será descontinuado. Ele permanece fora do
   monorepo por enquanto. Quando o usuário fornecer o código real, uma nova ADR (0003) deve
   registrar a decisão informada por auditoria real, conforme Prompt Mestre §6.1: mantê-lo como
   cliente desktop especializado, migrar funções gradualmente, reutilizar o núcleo Python no
   backend, ou empacotar o frontend web via Tauri/Electron.
3. SQLite é permitido apenas em modo demonstração/desenvolvimento unitário, nunca como banco
   principal (Prompt Mestre §6.2), mesmo que o app PyQt5 atual use SQLite hoje segundo a
   apresentação (slide 3, `AP-06`).

## Consequências

- Risco de retrabalho: se o app PyQt5 contiver lógica científica validada (ex.: geração TPMS,
  cálculo de porosidade, banco de 32+ materiais com 43+ DOIs), ela será reimplementada do zero
  na Fase 2 até que o código real seja auditado e migrado/reutilizado.
- O scaffold desta sessão cria apenas estrutura e configuração, sem lógica de negócio, para
  minimizar esse retrabalho.

## Próxima revisão

Assim que o repositório/pasta com o app PyQt5 for conectado, reabrir esta decisão como ADR-0003.
