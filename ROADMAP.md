# Roadmap — BioMatCAD Nexus

Este roadmap reflete o estado real após o Incremento 2.1 (Fase 2, entregue parcialmente
bloqueado — ver `IMPLEMENTATION_STATUS.md` e ADR-0007). Não é uma promessa de prazos; é uma
priorização técnica, atualizada a cada incremento aceito. Ver `REQUIREMENTS_MATRIX.md` para o
mapeamento completo de requisitos e `docs/adr/` para as decisões que o sustentam.

## Feito

- **Fase 1 (Incrementos 1 e 1.1)**: fundação executável — auth `DEV_AUTH`, estado operacional
  (Pesquisa/Laboratório/suíte clínica), modelos iniciais, frontend com landing/login/dashboard,
  histórico Git preservado em bundle.
- **Fase 2 (Incremento 2.1)**: primeira vertical funcional do núcleo BioMatCAD — material
  documentado → projeto → receita BioMatCEM → job geométrico → worker C#/PicoGK → scaffold
  Gyroid → métricas → artefatos → visualização 3D. **Parcialmente bloqueado**: o worker
  compila e tem seu contrato testado, mas a execução real do PicoGK está bloqueada neste
  sandbox (ausência de runtime nativo linux-x64 no pacote oficial 2.2.0 — ver ADR-0007).

## Próximo (prioridade, nesta ordem)

1. **Desbloquear o worker geométrico.** Sem isso, a Fase 3 não deve começar (condição explícita
   do Prompt Mestre). Dois caminhos não tentados nesta sessão:
   - Executar `apps/geometry-worker` em um ambiente Windows ou macOS real (onde o pacote PicoGK
     2.2.0 traz runtime nativo oficial) — caminho mais rápido, sem mudança de código.
   - Investigar um build nativo do PicoGK a partir do código-fonte C++ para linux-x64 —
     caminho mais lento, exige avaliação de licença/suporte antes de adotar.
   Após desbloquear: verificar geração real de scaffold, determinismo (mesma seed ⇒ mesmo STL),
   geração de thumbnail, e reavaliar suporte a VDB.
2. **Carregar dados reais de materiais** (AP-07: 32+ materiais, 43+ referências DOI) no catálogo
   que hoje está vazio — sem inventar nenhum valor, só o que estiver expressamente nos
   documentos-fonte auditados (`docs/SOURCE_DOCUMENTS.md`) ou claramente rotulado como
   sintético.
3. **RBAC básico por organização/projeto** (`PM-ONLY-04h`) — hoje só existe `role` de string
   simples; falta hierarquia institucional real antes de abrir o sistema a múltiplas
   organizações de verdade.
4. **Segunda topologia TPMS** (Schwarz-P ou IWP) como `schema_version "1.1.0"` do BioMatCEM,
   seguindo o padrão de versionamento do ADR-0006 — só depois do worker desbloqueado, para não
   acumular funcionalidade não verificável.
5. **FEM (Fase 2, continuação)** — explicitamente fora de escopo do Incremento 2.1; só deve
   começar depois que a vertical geométrica estiver realmente executável.

## Mais adiante (fora de escopo dos próximos incrementos)

- DICOM/imagens médicas, LIMS/ELN/terapia celular, prontuário/telemedicina/agenda clínica —
  `PM-ONLY-01/02/03` — todos fora de escopo até o núcleo científico (CAD/FEM/materiais/ML)
  estar consolidado, por decisão de sequenciamento, não por reavaliação do escopo confirmado em
  ADR-0001/ADR-0003.
- Matriz regulatória completa (`PM-ONLY-05`) — depende dos módulos clínicos acima existirem
  primeiro.
- OIDC/OAuth2.1+PKCE, MFA/WebAuthn, step-up authentication (`PM-ONLY-04e/04f/04g`) — substituir
  `DEV_AUTH` antes de qualquer uso com dados reais (nunca clínicos, mesmo depois).

## Princípio de sequenciamento

Nenhum incremento futuro deve ser apresentado como mais completo do que realmente é. Se um
bloqueio de ambiente (como o do PicoGK neste incremento) se repetir, o padrão a seguir é o
mesmo: implementar o máximo do contrato possível, testar genuinamente o que não depende do
bloqueio, documentar a evidência do bloqueio, e declarar o incremento parcialmente bloqueado —
nunca simular sucesso.
