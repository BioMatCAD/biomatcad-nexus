# ADR-0004: Semântica corrigida da suíte clínica e da chave mestra

- Status: Aceita
- Data: 2026-07-27 (Incremento 1.1)
- Decisor: Adler Lima Botelho de Azevedo (usuário), correção solicitada explicitamente

## Contexto

No Incremento 1, o campo `clinical_suite_enabled` de `GET /api/v1/system/status` foi implementado
incorretamente: o cálculo somava Laboratório aos estados "clínicos" (`clinical_kinds` incluía
`LABORATORY`) e usava lógica "qualquer um habilitado" (OR) em vez de "os três simultaneamente"
(AND). O endpoint de ativação (`POST /operational-state/activate`) também permitia ativar
`clinical_pilot`/`clinical_production` individualmente, uma chave por vez, sem garantia de
atomicidade entre eles.

O usuário identificou a divergência e especificou o comportamento correto.

## Decisão

1. **Dois grupos distintos e não combináveis**:
   - Contextos independentes: `research` (habilitado por padrão) e `laboratory` (desabilitado
     por padrão), cada um ativável isoladamente via `POST /operational-state/activate`.
   - Suíte clínica: `clinical_test`, `clinical_pilot`, `clinical_production` — sempre
     controlados em conjunto, nunca individualmente.
2. **Endpoints dedicados e atômicos** para a suíte clínica:
   `POST /api/v1/system/clinical-suite/activate` e `.../deactivate`. Ambos:
   - operam em uma única transação de banco (todos os três ou nenhum);
   - usam a MESMA chave mestra (`OPERATIONAL_STATE_MASTER_KEY`) — nunca uma segunda chave;
   - exigem um usuário com papel administrativo (`require_admin`);
   - registram `AuditEvent` com estado anterior, estado posterior, justificativa e identidade
     do administrador;
   - suportam expiração opcional (`expires_at`), avaliada em tempo de leitura
     (`OperationalState.is_effectively_enabled`), sem exigir job de expiração em background
     nesta fase.
3. `POST /operational-state/activate` passa a **rejeitar** (`400`) qualquer tentativa de ativar
   `clinical_test`, `clinical_pilot` ou `clinical_production` — essa é a barreira que impede a
   recorrência do bug original (ativação parcial fora da transação atômica).
4. `clinical_suite_enabled` em `GET /api/v1/system/status` é recalculado como
   `all(efetivamente_habilitado(k) for k in {clinical_test, clinical_pilot, clinical_production})`,
   nunca incluindo `laboratory` ou `research`.

## Consequências

- Qualquer código, teste ou texto de documentação anterior que tratasse "suíte clínica" e
  "laboratório" como sinônimos ou como um conjunto único está incorreto e foi corrigido nesta
  sessão (routers, schemas, frontend, testes, `REQUIREMENTS_MATRIX.md`, `IMPLEMENTATION_STATUS.md`).
- A UI (cartão de login, dashboard) agora exibe os dois indicadores separadamente.
- Rollback integral: qualquer falha durante a gravação dos três estados é revertida por
  completo (`db.rollback()` + `ClinicalSuiteTransactionError`), verificado por teste dedicado
  (`test_activation_rolls_back_completely_on_failure`).
- RBAC ainda não é o completo do Prompt Mestre §9 (17 perfis) — `require_admin` é um controle
  mínimo (`role in {admin, superadmin}`), suficiente para não deixar a ativação sem nenhuma
  autorização, mas não substitui o RBAC/ABAC completo (`PM-ONLY-04`, backlog).
