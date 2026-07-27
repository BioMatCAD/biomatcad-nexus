# ADR-0003: O Prompt Mestre é a especificação de produto; a tese é fonte científica, não teto de escopo

- Status: Aceita
- Data: 2026-07-27
- Decisor: Adler Lima Botelho de Azevedo (usuário)

## Contexto

O ADR-0001 registrou a divergência entre o escopo da proposta de tese/apresentação (núcleo
computacional: CAD, FEM, banco de materiais, ML, otimização) e o escopo do Prompt Mestre
(que soma módulos clínicos e laboratoriais: LIMS, ELN, biobanco, terapia celular, chain of
identity/custody, prontuário, FHIR, agenda, telemedicina). Esta sessão havia interpretado a
frase da Tese §8.1 — *"Independência experimental: Abordagem computacional, sem dependência de
laboratórios"* — como uma delimitação de escopo que poderia entrar em conflito com os módulos
clínicos/laboratoriais do Prompt Mestre.

O usuário corrigiu essa interpretação explicitamente.

## Decisão

1. **O Prompt Mestre é a especificação autoritativa do produto completo BioMatCAD Nexus.** A
   tese e a apresentação são fontes científicas e históricas do núcleo computacional, mas não
   definem nem limitam o escopo total da plataforma como produto de software.
2. A frase "abordagem computacional, sem dependência de laboratórios" (Tese §8.1) descreve a
   **metodologia e a viabilidade do trabalho acadêmico de doutorado** apresentado — ou seja,
   por que o projeto de tese, especificamente, é executável sem depender de infraestrutura
   laboratorial própria do candidato. **Não é uma proibição ou exclusão de expansão futura da
   plataforma** para LIMS, ELN, biobanco, terapia celular, chain of identity, chain of custody,
   prontuário, FHIR, agenda ou módulos clínicos em geral.
3. Todos os requisitos `PM-ONLY-*` da `REQUIREMENTS_MATRIX.md` são confirmados como requisitos
   válidos do produto BioMatCAD Nexus, com status `CONFIRMED-PRODUCT-SCOPE`.
4. A rastreabilidade de origem é preservada: esses requisitos continuam identificados como
   originados no Prompt Mestre, não na tese ou na apresentação. **Nenhuma afirmação sobre os
   documentos científicos deve ser reescrita para sugerir que eles descrevem ou aprovam o
   escopo clínico/laboratorial** — essa distinção evita atribuir aos documentos afirmações que
   eles não apresentam (ver também a nota de honestidade técnica em
   `docs/SOURCE_DOCUMENTS.md`).

## Consequências

- `REQUIREMENTS_MATRIX.md` é atualizado: os 5 itens `PM-ONLY-*` passam de "Aguardando
  confirmação"/bloqueado para `CONFIRMED-PRODUCT-SCOPE`, cada um mantendo a coluna Fonte como
  "Prompt Mestre §X", não a tese/apresentação.
- O texto de `docs/SOURCE_DOCUMENTS.md` (achado `SCOPE-CONFLICT-01`) permanece factualmente
  correto quanto ao que os documentos contêm (nenhuma menção a LIMS/clínica/telemedicina) — o
  que muda é a interpretação de que isso representaria um "conflito" a resolver; agora está
  registrado como complementaridade de fontes (científica vs. produto), não como contradição.
- Módulos `PM-ONLY-*` continuam sujeitos aos princípios inegociáveis do Prompt Mestre (Seção 3):
  quatro estados operacionais, uso clínico bloqueado por padrão, nenhuma alegação de conformidade
  regulatória sem validação externa formal.
- Este ADR não autoriza retroativamente nenhuma alegação de que a tese/apresentação preveem,
  descrevem ou validam cientificamente os módulos clínicos/laboratoriais — apenas que o produto
  de software pode incluí-los por decisão do usuário, documentada aqui.
