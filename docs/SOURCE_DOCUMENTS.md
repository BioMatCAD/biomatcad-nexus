# Inventário de Documentos-Fonte — BioMatCAD Nexus

Fase 0 — Auditoria inicial obrigatória (Seção 4 do Prompt Mestre).

## Varredura realizada

Comando equivalente a `rg --files | rg -i '\.pdf$'` executado sobre todos os diretórios
acessíveis nesta sessão:

- `uploads/` (arquivos anexados nesta conversa)
- `.projects/019ac059-f5bf-754d-b7a7-46f1378097eb/` (projeto de conhecimento "documentação
  doutorado", importado do Claude.ai)

**Resultado:** nenhum repositório de código (`biomatcad-nexus/` ou monorepo equivalente) foi
encontrado em nenhum caminho acessível. O projeto de conhecimento contém 48 PDFs — nenhum
correspondia à tese ou à apresentação (eram certificados de curso, diploma/histórico escolar,
currículo Lattes e 3 rascunhos de um livro didático sobre PicoGK). Os dois documentos corretos
foram então enviados diretamente pelo usuário nesta conversa.

## Documento 1 — Apresentação

| Campo | Valor |
|---|---|
| Caminho | `uploads/BioMatCAD_Apresentacao_Doutorado_1.pdf` |
| Nome | BioMatCAD – Plataforma Computacional para Biomateriais Nanoestruturados |
| Tipo | Apresentação (slides, formato 16:9), gerada via PptxGenJS/LibreOffice Impress |
| SHA-256 | `72bb700114bacaed24b3635832d171fdb5284c1b9a48d4af6a6656014d9f5a0a` |
| Páginas | 4 (slides numerados 01/04 a 04/04) |
| Autor | Adler Lima Botelho de Azevedo |
| Data de criação do arquivo | 27/07/2026 (conversão/exportação; conteúdo referencia Nov/2025) |
| Afiliação declarada | PPGBIOTEC / UFBA · Novembro 2025 |
| Tamanho | 411.291 bytes |

**Conteúdo utilizado (íntegra, 4 slides):**

1. **Slide 1 — Contextualização e desafio.** Compara método experimental tradicional
   (6–12 meses/iteração) vs. método BioMatCAD computacional (4–8 horas/ciclo), alegando
   aceleração de "até ~95%". Cita Zhu et al. 2020, Minardi et al. 2020, Perier-Metz et al. 2022.
2. **Slide 2 — Objetivos.** Objetivo geral: plataforma para projeto racional e otimização
   in silico de biomateriais nanoestruturados para aplicações ortopédicas, integrando CAD, FEM,
   banco de dados de materiais e IA local. Quatro eixos: integração de módulos, ML local,
   otimização multiobjetivo, validação científica.
3. **Slide 3 — Arquitetura da plataforma (estado atual declarado).** Seis módulos: CAD 3D
   paramétrico, Simulação FEM, Banco de Materiais, LLM Local, Imagens Médicas, CAM/Fabricação,
   Cristalografia, Otimização. Stack declarada: **Python, PyQt5, SQLite, Ollama, LM Studio,
   PicoGK C#, GGUF, Marching Cubes, PyInstaller** — ou seja, **aplicativo desktop**, não
   cliente-servidor web. Sinais inter-módulos PyQt5 nomeados (`scaffold_exported`,
   `code_generated`, `stl_ready`, `scaffold_suggested`). Banco de materiais: 32+ materiais,
   43+ referências DOI (fosfatos de cálcio β-TCP/HAp/BCP, vidros bioativos 45S5/13-93, metais
   Ti-6Al-4V/CoCr, polímeros PLA/PCL/PLGA). TPMS: Gyroid, Schwarz-P, IWP. Fórmula Gibson-Ashby
   citada (E*/Es = C·ρ̄ⁿ, n=2) e módulo de Weibull m≈4,39 (DLP).
4. **Slide 4 — Metodologia e fluxo (7 etapas).** Requisitos clínicos → design paramétrico →
   seleção de materiais → simulação FEM → predição biológica (ML) → otimização multiobjetivo →
   validação/exportação. Parâmetros cristalográficos do β-TCP (grupo espacial R3c: a=10,4352 Å,
   c=37,4029 Å), transformação β→α acima de 1125 °C, fabricação por robocasting/DLP. Menciona
   "Módulo DICOM equiv. InVesalius (32 func.)" e "CrystalDB Downloader: COD (~450k) + PDB
   (~200k) com catálogo SQLite".

**Requisitos derivados:** ver `REQUIREMENTS_MATRIX.md`, IDs `AP-01` a `AP-09`.

## Documento 2 — Proposta de Tese

| Campo | Valor |
|---|---|
| Caminho | `uploads/Projeto_Tese_COMPLETO_com_Figuras_e_Citacoes (1).pdf` |
| Nome no arquivo | "COMPLETO com Figuras e Citações" |
| Título real (página de rosto) | **PROPOSTA DE PROJETO DE TESE DE DOUTORADO** — "Plataforma Computacional para Projeto Assistido de Biomateriais Nanoestruturados para Aplicações Ortopédicas" |
| Tipo | Proposta/projeto de tese (pré-qualificação), não a tese defendida/completa |
| SHA-256 | `392955a7dfd3b0235f7c11d705cb571feb17bb06a50b22af953d500545c9b60c` |
| Páginas | 12 |
| Candidato | Adler Lima Botelho de Azevedo |
| Orientador | Prof. Dr. Antonio Ferreira da Silva |
| Coorientador | Prof. Dr. Gildasio de Cerqueira Daltro |
| Instituição | UFBA — Instituto de Ciências da Saúde — PPGBiotec |
| Área/linha | Área 3 (Biofotônica e Nanotecnologia); linha D920231 |
| Data | Salvador, 01 de novembro de 2025 |
| Tamanho | 1.016.200 bytes |

**⚠️ Nota de honestidade técnica (Princípio 3.1 do Prompt Mestre):** apesar do nome do
arquivo sugerir um documento "completo", o conteúdo é uma **proposta de projeto de tese**
(pré-execução), com cronograma de 48 meses ainda a decorrer (defesa prevista para o mês 48) e
metas declaradas como alvos futuros, não resultados obtidos (ex.: "modelos de ML validados
(acurácia > 85%)" é uma meta de Fase 7, não uma métrica já alcançada). Este relatório trata
todo o conteúdo do documento como **intenção/plano**, não como funcionalidade implementada.

**Conteúdo utilizado (íntegra, 9 seções + referências):**

1. **Resumo executivo** — mesma tese central da apresentação.
2. **Arquitetura da plataforma** — declara "arquitetura modular cliente-servidor, com
   **backend em Python e frontend web-based em React.js**" e seis módulos via API REST
   (CAD 3D Engine, FEM Simulator, Materials Database, ML Predictor, Multi-Objective Optimizer,
   Visualization UI). **Isto diverge da Apresentação (Doc. 1, slide 3)**, que descreve o estado
   atual como app desktop PyQt5/SQLite sem menção a React ou API REST — ver `ARCH-DIVERGE-01`
   na matriz.
3. **Metodologia e fluxo de trabalho** — mesmo ciclo iterativo de 4–8h; 7 fases sequenciais ao
   longo de 48 meses (revisão bibliográfica → CAD/BD → FEM → ML → otimização → integração/UI/
   validação → documentação/tese).
4. **Cronograma** — Gantt de 48 meses; marcos: base de dados (mês 6), qualificação (mês 24),
   plataforma funcional (mês 42), defesa (mês 48).
5. **Otimização multiobjetivo** — NSGA-II, fronteira de Pareto, objetivos: resistência
   mecânica, porosidade, biocompatibilidade, custo estimado.
6. **Machine learning para predição biológica** — dataset alvo >500 amostras da literatura;
   features (composição, tamanho de partícula, área superficial, carga de superfície, energia
   de banda); algoritmos candidatos (Random Forest baseline, SVM, redes neurais); validação
   k-fold (k=5); métricas R², MAE, RMSE; exportação em pickle/ONNX.
7. **Resultados esperados e produtos** — plataforma funcional; banco >200 materiais
   caracterizados; modelos de ML validados (meta de acurácia >85%); repositório GitHub
   open-source; manual técnico; ≥3 artigos Qualis A1-B1; registro de software no INPI.
8. **Análise de viabilidade** — viabilidade técnica justificada explicitamente por
   **"Independência experimental: Abordagem computacional, sem dependência de laboratórios"**
   — ver `SCOPE-CONFLICT-01` na matriz, pois contradiz o escopo de LIMS/laboratório/terapia
   celular do Prompt Mestre. Viabilidade cronológica (48 meses) e ineditismo (ausência de
   plataforma similar integrando CAD+FEM+ML+Otimização para biomateriais ortopédicos).
9. **Referências bibliográficas** — 40 referências completas (ABNT), todas com autor/ano/
   periódico/volume/página, cobrindo biomateriais, FEM/mecanobiologia, materials informatics/ML,
   otimização evolutiva e scaffolds. Nenhuma referência a normas regulatórias, FHIR, DICOM
   (exceto menção indireta via apresentação), LIMS, terapia celular ou telemedicina.
10. **Assinaturas** — candidato, orientador, coorientador (documento formal de proposta).

**Requisitos derivados:** ver `REQUIREMENTS_MATRIX.md`, IDs `TP-01` a `TP-14`.

## Divergências e achados que bloqueiam avanço automático

| ID | Achado | Documentos envolvidos | Ação recomendada |
|---|---|---|---|
| `ARCH-DIVERGE-01` | Tese propõe backend Python + frontend React/API REST; Apresentação descreve stack atual como desktop PyQt5/SQLite sem API. `memory.md` do usuário confirma que o app real hoje é PyQt5 desktop de 8 módulos. | Tese §2 vs. Apresentação slide 3 vs. estado real (fora dos 2 PDFs) | Decidir por ADR: manter PyQt5 como cliente científico e construir API/web por cima (opção já prevista no Prompt Mestre §6.1), ou migrar. Não presumir React já implementado. |
| `SCOPE-CONFLICT-01` | Nenhum dos dois documentos-fonte menciona prontuário eletrônico, agenda clínica, portal do paciente, telemedicina/WebRTC, LIMS, ELN, terapia celular, chain of custody, FHIR ou PACS. A viabilidade da tese é justificada exatamente pela **ausência** de dependência de laboratório/clínica. Todo o escopo das Seções 9–12 do Prompt Mestre (identidade clínica, plataforma clínica digital, telemedicina, LIMS/terapia celular) **não tem base nos documentos científicos anexados**. | Prompt Mestre §§9–12 vs. Tese/Apresentação (ausentes) | Reportado ao usuário como achado crítico antes de gerar requisitos desse escopo — ver mensagem de resposta desta sessão. Requisitos correspondentes marcados como `Fonte: Prompt Mestre (sem base documental)` na matriz, não como `Fonte: Tese/Apresentação`. |
| `CLAIM-UNVERIFIED-01` | "Aceleração de até ~95%" e "acurácia > 85%" são metas/estimativas do projeto, não resultados medidos. | Apresentação slide 1; Tese §7.1 | Tratar como meta de aceite (critério de validação), nunca como resultado já alcançado, em qualquer material derivado (site, relatório, README). |
