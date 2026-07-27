# ADR-0002: Stack tecnológica principal do BioMatCAD Nexus

- Status: **Aceita — oficial** (atualizado em 2026-07-27; substitui o caráter provisório da
  versão anterior deste ADR)
- Data original: 2026-07-27
- Decisor: Adler Lima Botelho de Azevedo (usuário)

## Contexto

A versão original deste ADR (mesma data) era provisória: o app PyQt5 mencionado no `memory.md`
do usuário não havia sido fornecido para auditoria, então a escolha de stack ficou condicionada
a uma revisão futura. O usuário confirmou explicitamente, em mensagem posterior, que:

1. React + FastAPI + PostgreSQL + Redis + MinIO deve ser adotado **oficialmente** como
   arquitetura principal, sem caráter provisório.
2. O app PyQt5/SQLite é uma implementação anterior ou referência histórica, não um bloqueador
   da arquitetura web.
3. O PyQt5 poderá ser auditado e aproveitado posteriormente, se e quando o código for
   disponibilizado, mas seu desenvolvimento não deve esperar por isso.

## Decisão

1. **Arquitetura oficial adotada** para o BioMatCAD Nexus:
   - Frontend: React + TypeScript + Vite, roteamento client-side, cliente de API tipado a
     partir dos contratos OpenAPI.
   - Backend: FastAPI (Python), configuração tipada por ambiente, OpenAPI versionado.
   - Banco principal: PostgreSQL. SQLite continua permitido **somente** em modo demonstração
     ou teste unitário local (Prompt Mestre §6.2), nunca como banco de produção.
   - Cache/locks/fila: Redis.
   - Object storage S3-compatível: MinIO (local) / equivalente gerenciado (nuvem/híbrido).
   - Comunicação inicial via REST com contratos OpenAPI versionados (`packages/contracts`).
   - Workers científicos (`apps/compute-worker`, Python) e worker geométrico C#/.NET com
     PicoGK/ShapeKernel (`apps/geometry-worker`) mantidos como serviços separados do backend
     principal, conforme Prompt Mestre §6.3–6.4.
   - Implantação em três modos, conforme Prompt Mestre §7: local monousuário, rede local
     multiusuário (Docker Compose), e frontend estático demonstrativo no GitHub Pages
     (dados exclusivamente sintéticos, sem backend real — Prompt Mestre §3.3/§7.1).

2. **PyQt5 (app existente, não auditado nesta sessão):** classificado como **legado/referência
   histórica e módulo desktop auxiliar em potencial** — não como arquitetura principal e não
   como bloqueador de progresso. Quando o código for disponibilizado, uma ADR futura registrará,
   com base em auditoria real (não em suposição), qual das opções do Prompt Mestre §6.1 se
   aplica: mantê-lo como cliente desktop especializado, migrar funções gradualmente para o
   frontend web, reutilizar seu núcleo Python no backend FastAPI, ou empacotá-lo via
   Tauri/Electron. Até lá, `apps/desktop/README.md` continua registrando essa pendência.

## Consequências

- O Incremento 1 da Fase 1 (fundação executável: landing, login, dashboard, API de
  health/status, modelos de Organização/Usuário/EstadoOperacional/AuditEvent) é implementado
  integralmente sobre esta stack, sem esperar por decisão sobre o PyQt5.
- Risco de retrabalho científico permanece registrado (mesma ressalva da versão anterior deste
  ADR): se o PyQt5 contiver lógica já validada (TPMS, porosidade, banco de 32+ materiais), ela
  ainda pode ser reimplementada nas Fases 2+ até auditoria real do código.
- Este ADR não immplica qualquer alegação de que a stack foi validada em produção — apenas que é
  a arquitetura-alvo oficial para todo desenvolvimento a partir de agora.

## Registro de mudança

| Data | Mudança |
|---|---|
| 2026-07-27 | Criação como decisão provisória, condicionada a auditoria futura do PyQt5. |
| 2026-07-27 | Atualizado para status oficial/definitivo, por decisão explícita do usuário, sem alterar a arquitetura escolhida — apenas remove a condicionalidade. |
