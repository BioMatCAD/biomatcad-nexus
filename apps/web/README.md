# apps/web — Frontend React/TypeScript/PWA

**Status: Incremento 1 implementado e testado (2026-07-27).** Landing, login (JWT em memória),
dashboard autenticado com sidebar, tema claro/escuro, modo demonstração para GitHub Pages — 6
testes Vitest passando, builds normal e de demo executados com sucesso. Ver
`IMPLEMENTATION_STATUS.md` na raiz para evidências completas.

**Ainda não implementado**: TanStack Query, Three.js/R3F, Plotly/ECharts, PWA/service worker,
i18n (en/es — pt-BR é o único idioma hoje, sem framework de i18n ainda), design system
compartilhado formal (`packages/ui`).

## Propósito

Frontend principal: React + TypeScript estrito + Vite + React Router (com suporte a base path do GitHub Pages) + TanStack Query + Three.js/R3F para visualização 3D + Plotly/ECharts para gráficos científicos. PWA com service worker. i18n pt-BR padrão.

## Fonte no Prompt Mestre

Seção 6.1

## Como executar

Ver seção "Frontend" em `README.md` (raiz do repositório).

## Próximo passo

Ver `REQUIREMENTS_MATRIX.md` e `docs/adr/` para requisitos e decisões associadas antes do
próximo incremento.
