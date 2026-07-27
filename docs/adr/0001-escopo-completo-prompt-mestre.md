# ADR-0001: Escopo do BioMatCAD Nexus — Prompt Mestre completo vs. núcleo da tese

- Status: Aceita
- Data: 2026-07-27
- Decisor: Adler Lima Botelho de Azevedo (usuário/candidato)

## Contexto

A auditoria da Fase 0 (`docs/SOURCE_DOCUMENTS.md`, `REQUIREMENTS_MATRIX.md`) mostrou que os
dois documentos-fonte do projeto de doutorado — a proposta de tese e a apresentação —
descrevem um escopo estritamente computacional: CAD 3D, FEM, banco de materiais, ML de
predição biológica e otimização multiobjetivo. A própria tese (§8.1) justifica sua viabilidade
técnica citando "abordagem computacional, sem dependência de laboratórios". Nenhum dos dois
documentos menciona prontuário eletrônico, agenda clínica, telemedicina, LIMS, ELN, terapia
celular ou identidade clínica institucional (Keycloak/RBAC de 17 perfis).

O `Prompt_Mestre_BioMatCAD_Nexus.md`, por outro lado, especifica uma plataforma
significativamente mais ampla, incluindo esses módulos clínicos/laboratoriais (Seções 9–12).

## Decisão

Seguir o **escopo completo do Prompt Mestre**, incluindo os módulos sem base direta na tese/
apresentação (`PM-ONLY-01` a `PM-ONLY-05` na matriz de requisitos). Decisão tomada
explicitamente pelo usuário após ser confrontado com a divergência de escopo.

## Consequências

- O sistema resultante extrapola o projeto de doutorado documentado. Isso deve ficar explícito
  em qualquer material voltado à banca, orientadores ou publicação, para não sugerir aprovação
  acadêmica de um escopo que os orientadores não avaliaram.
- Módulos clínicos/laboratoriais herdam os princípios da Seção 3 do Prompt Mestre: quatro
  estados operacionais (Pesquisa/Laboratório/Piloto clínico/Produção clínica), uso clínico
  bloqueado por padrão até aprovação institucional formal, e proibição de alegar conformidade
  regulatória sem validação externa.
- O roadmap de fases (Seção 29 do Prompt Mestre) é adotado como plano de engenharia,
  independente do cronograma acadêmico de 48 meses da tese (que cobre só Fases 0–3
  aproximadamente).
- Este ADR não altera a prioridade relativa: os módulos `AP-*`/`TP-*` (com base científica real)
  permanecem P0 no MVP vertical (Seção 28 do Prompt Mestre); os módulos `PM-ONLY-*` entram no
  backlog nas fases 5–7, não na Fase 1.

## Alternativas consideradas

1. **Núcleo científico apenas** — mais fiel aos documentos auditáveis, menor risco regulatório,
   mas não atende ao pedido explícito do usuário.
2. **Escopo completo, mas adiado** — registrar como visão de longo prazo sem iniciar scaffold
   dos módulos clínicos agora. Rejeitada porque o usuário pediu explicitamente para seguir o
   Prompt Mestre integralmente já na fundação (Fase 1).
