# Política de Registro de Fontes (Incremento 2.3, Rodada 1)

Este documento registra, como **candidatas futuras**, as bases de dados científicas e de
fornecedores mais relevantes para o BioMatCAD Nexus. **Nenhum conector real para qualquer uma
delas é implementado nesta rodada** — nenhuma chamada de rede contra essas bases foi feita, e
nenhum dado copiado/raspado delas. O objetivo é exclusivamente documentar o que precisaria ser
avaliado antes de qualquer implementação futura, incluindo os pontos de licenciamento que
podem bloquear ou condicionar a redistribuição.

Toda linha desta tabela usa apenas informação pública sobre a própria existência e propósito
declarado de cada fonte — não é uma alegação de ter revisado o texto legal completo de cada
licença; isso é trabalho de uma rodada futura, antes de qualquer implementação de conector real.

## Bases candidatas

### PubChem (NIH/NLM)

- **Autoridade**: National Center for Biotechnology Information (NCBI), NIH, EUA.
- **Identificadores**: CID (Compound ID), SID (Substance ID).
- **Tipo de dado**: substâncias/compostos químicos, propriedades físico-químicas calculadas e
  experimentais, estrutura molecular.
- **Licença/termos**: dados de domínio público do governo dos EUA em geral, mas PubChem agrega
  dados de terceiros com termos variáveis por registro — **a permissão de redistribuição precisa
  ser verificada registro a registro em uma rodada futura**, não pode ser assumida em bloco.
- **API/distribuição**: PUG-REST/PUG-View (API pública documentada) e dumps em massa via FTP.
- **Periodicidade futura sugerida**: sob demanda (consulta por CID/nome), não um sincronismo em
  massa nesta fase.
- **Limitações conhecidas**: volume muito grande; qualidade heterogênea por registro (alguns
  provenientes de fornecedores, outros de literatura revisada) — reforça a necessidade do campo
  `evidence_type` já modelado nesta rodada.
- **Redistribuição**: **não confirmada** nesta rodada — tratar como `RedistributionStatus.UNKNOWN`
  por padrão até revisão específica.

### ChEBI (EMBL-EBI)

- **Autoridade**: European Bioinformatics Institute (EMBL-EBI).
- **Identificadores**: ChEBI ID.
- **Tipo de dado**: ontologia de entidades químicas de relevância biológica, com relações
  hierárquicas (é-um, tem-parte).
- **Licença/termos**: Creative Commons (CC BY 4.0) segundo a própria EMBL-EBI para grande parte
  do conteúdo — ainda assim, **confirmar a licença exata vigente no momento da implementação**,
  já que políticas de licenciamento de bases públicas podem mudar.
- **API/distribuição**: API SOAP/REST e download em massa (OBO/OWL/SDF).
- **Periodicidade futura sugerida**: sob demanda.
- **Limitações conhecidas**: foco em relevância biológica, não em todas as substâncias químicas
  existentes.
- **Redistribuição**: **permitida sob os termos CC BY, se confirmados** — mesmo assim, tratar
  como `UNKNOWN` até essa confirmação explícita ocorrer em rodada futura dedicada.

### ChEMBL (EMBL-EBI)

- **Autoridade**: European Bioinformatics Institute (EMBL-EBI).
- **Identificadores**: ChEMBL ID.
- **Tipo de dado**: bioatividade de moléculas (ensaios, alvos, dados farmacológicos/dose-resposta).
- **Licença/termos**: CC BY-SA 3.0 segundo a própria EMBL-EBI — **a variante "compartilhada
  igual" (SA) tem implicações de redistribuição diferentes de CC BY simples; precisa ser avaliada
  com cuidado antes de qualquer redistribuição futura**.
- **API/distribuição**: API REST e download em massa (SQLite/PostgreSQL dumps).
- **Periodicidade futura sugerida**: sob demanda.
- **Limitações conhecidas**: focado em bioatividade de fármacos/candidatos, não em materiais
  estruturais.
- **Redistribuição**: **condicionada aos termos CC BY-SA** — tratar como `UNKNOWN` até
  confirmação.

### Crossref

- **Autoridade**: organização sem fins lucrativos mantida por editoras acadêmicas.
- **Identificadores**: DOI.
- **Tipo de dado**: metadados bibliográficos (título, autores, veículo, ano, referências
  cruzadas) — **não** o texto completo dos artigos.
- **Licença/termos**: metadados geralmente sob CC0 (domínio público) segundo a própria Crossref,
  mas isso cobre apenas os METADADOS, nunca o conteúdo integral do artigo referenciado.
- **API/distribuição**: API REST pública (`api.crossref.org`), sem necessidade de chave para uso
  básico.
- **Periodicidade futura sugerida**: sob demanda, no momento em que uma `BibliographicReference`
  precisar de metadados confirmados por DOI.
- **Limitações conhecidas**: apenas metadados, não conteúdo.
- **Redistribuição**: metadados **provavelmente permitidos (CC0)**, mas ainda assim tratar como
  `UNKNOWN` até confirmação formal na rodada de implementação.

### Europe PMC / PubMed

- **Autoridade**: EMBL-EBI (Europe PMC) / NCBI-NLM-NIH (PubMed).
- **Identificadores**: PMID, PMCID.
- **Tipo de dado**: metadados bibliográficos biomédicos, resumos, e (quando disponível em
  repositórios de acesso aberto) texto completo.
- **Licença/termos**: metadados geralmente abertos; texto completo varia por artigo (muitos sob
  licenças restritivas de editoras, mesmo quando indexados) — **nunca assumir acesso aberto ao
  texto completo apenas por estar indexado**.
- **API/distribuição**: Europe PMC REST API e E-utilities do NCBI.
- **Periodicidade futura sugerida**: sob demanda.
- **Limitações conhecidas**: mistura de conteúdo aberto e fechado no mesmo índice.
- **Redistribuição**: **variável por artigo** — nunca `ALLOWED` em bloco; sempre avaliar por
  registro.

### Crystallography Open Database (COD)

- **Autoridade**: consórcio acadêmico internacional (mantido por instituições como a
  Universidade de Vilnius).
- **Identificadores**: COD ID.
- **Tipo de dado**: estruturas cristalográficas (arquivos CIF) de compostos orgânicos,
  inorgânicos e metal-orgânicos.
- **Licença/termos**: o próprio COD declara os dados como de domínio público/CC0 para a maior
  parte do conteúdo — **ainda assim, confirmar por entrada, já que parte do conteúdo é derivada
  de publicações com direitos próprios**.
- **API/distribuição**: download em massa de arquivos CIF, além de uma API de consulta.
- **Periodicidade futura sugerida**: sob demanda, por accession específico.
- **Limitações conhecidas**: nenhum arquivo CIF é baixado ou incorporado nesta rodada — apenas
  metadados de referência (`CrystalStructureReference`) seriam armazenados numa implementação
  futura.
- **Redistribuição**: **tratar como `UNKNOWN` até confirmação por entrada**, apesar da postura
  geral aberta do projeto.

### RCSB PDB (Protein Data Bank)

- **Autoridade**: consórcio internacional (RCSB, PDBe, PDBj, BMRB).
- **Identificadores**: PDB ID.
- **Tipo de dado**: estruturas macromoleculares (proteínas, ácidos nucleicos) resolvidas
  experimentalmente.
- **Licença/termos**: o RCSB PDB declara os dados depositados como de domínio público — mas
  **atribuição aos depositantes originais é esperada** por convenção da comunidade, mesmo sem
  exigência legal estrita.
- **API/distribuição**: API REST (`data.rcsb.org`) e download em massa de arquivos PDB/mmCIF.
- **Periodicidade futura sugerida**: sob demanda.
- **Limitações conhecidas**: foco em macromoléculas biológicas, não em materiais de engenharia
  estrutural em geral.
- **Redistribuição**: **domínio público declarado**, mas ainda assim tratar como `UNKNOWN`
  internamente até a rodada de implementação confirmar e documentar a atribuição adequada.

### Bases de fornecedores comerciais (ex.: catálogos de materiais biocompatíveis)

- **Autoridade**: variável — cada fornecedor individual.
- **Identificadores**: SKU/catálogo próprio de cada fornecedor (nunca um identificador
  científico canônico — ver princípio 3 da rodada: produto de fornecedor nunca é sinônimo da
  entidade canônica).
- **Tipo de dado**: fichas técnicas comerciais, propriedades declaradas pelo fabricante
  (sempre rotuladas como `SUPPLIER_DECLARED`, nunca como `EXPERIMENTAL`).
- **Licença/termos**: **tipicamente restritiva** — a maioria dos catálogos comerciais não
  concede permissão de redistribuição de seu conteúdo integral; extração/raspagem sem
  autorização explícita do fornecedor é uma prática de alto risco legal.
- **API/distribuição**: varia por fornecedor; muitos não oferecem API pública.
- **Periodicidade futura sugerida**: **condicionada a acordo comercial ou autorização explícita
  do fornecedor** antes de qualquer implementação de conector.
- **Limitações conhecidas**: nenhuma padronização entre fornecedores; alto risco de dado
  desatualizado sem verificação periódica.
- **Redistribuição**: **por padrão `PROHIBITED` ou `UNKNOWN`** — nunca `ALLOWED` sem
  confirmação documental explícita do fornecedor específico.

## Regra geral desta política

Nenhuma fonte acima tem seu `redistribution_status` assumido como `ALLOWED` por este documento.
A tabela acima é um levantamento preliminar para orientar a priorização de uma rodada futura de
implementação de conectores — a confirmação formal da licença de cada fonte, incluindo consulta
jurídica quando necessário, é um passo obrigatório **antes** de qualquer `IngestionRun` real
contra qualquer uma dessas bases. Ver `LICENSING_AND_REDISTRIBUTION.md` para o tratamento de
licenciamento no nível de modelo de dados.
