# BioMatCAD Nexus

Plataforma integrada de engenharia computacional de biomateriais, laboratório, terapia celular
e saúde digital — projeto derivado do doutorado de Adler Lima Botelho de Azevedo
(PPGBiotec/UFBA) e do `Prompt_Mestre_BioMatCAD_Nexus.md`.

## Status real deste repositório (2026-07-27)

**Nada além de estrutura, documentação e configuração foi implementado nesta sessão.** Não há
backend funcional, frontend funcional, worker geométrico, banco de dados populado ou testes
passando. Qualquer afirmação de "completo" para qualquer módulo abaixo é falsa até que exista
código executado, testado e com evidência registrada — ver Seção 3.1 do Prompt Mestre.

O que existe de fato agora:

- Auditoria da Fase 0 concluída: `docs/SOURCE_DOCUMENTS.md`, `REQUIREMENTS_MATRIX.md`.
- Duas ADRs registrando decisões de escopo e stack: `docs/adr/0001-*.md`, `docs/adr/0002-*.md`.
- Estrutura de diretórios do monorepo (Seção 6 do Prompt Mestre), cada um com README explicando
  propósito e status "não implementado".
- Este README, `.editorconfig`, `.gitignore`, `.env.example`, `docker-compose.yml` (dev) e
  workflows de CI mínimos — todos ainda não testados em execução real.

## Por que o escopo é mais amplo que a tese de doutorado

O núcleo cientificamente validável (CAD 3D, FEM, banco de materiais, ML de predição biológica,
otimização multiobjetivo — requisitos `AP-*`/`TP-*` na matriz) vem diretamente da proposta de
tese e da apresentação de doutorado. Os módulos clínicos/laboratoriais (prontuário, FHIR,
telemedicina, LIMS, terapia celular — requisitos `PM-ONLY-*`) vêm exclusivamente do Prompt
Mestre, sem base nos documentos científicos. O usuário confirmou explicitamente que o escopo
completo deve ser seguido (ver `docs/adr/0001-escopo-completo-prompt-mestre.md`). Isso está
documentado para que ninguém confunda o escopo do software com o escopo do projeto de
doutorado aprovado pela banca/orientação.

## Estrutura

Ver árvore completa e propósito de cada diretório na Seção 6 do
`Prompt_Mestre_BioMatCAD_Nexus.md` e nos READMEs individuais de `apps/*`, `packages/*`,
`services/*`, `infra/*`, `data/*`, `tests/*`, `docs/*`.

## Quatro estados operacionais (Seção 3.2 do Prompt Mestre)

Todo módulo clínico/laboratorial deste sistema deve respeitar os quatro estados — Pesquisa,
Laboratório, Piloto clínico, Produção clínica — com uso clínico bloqueado por padrão até
aprovação institucional, ética, jurídica, de segurança e regulatória formal.

## Como executar hoje

Não há nada executável ainda. Este README será atualizado a cada incremento real (Seção 30 do
Prompt Mestre: nenhum ciclo termina sem lint, type check, testes e execução prática do fluxo).

## Documentos de referência

- `Prompt_Mestre_BioMatCAD_Nexus.md` — especificação completa (fornecida pelo usuário).
- `docs/SOURCE_DOCUMENTS.md` — inventário e proveniência dos documentos-fonte científicos.
- `REQUIREMENTS_MATRIX.md` — matriz de requisitos rastreável.
- `docs/adr/` — decisões de arquitetura registradas.
