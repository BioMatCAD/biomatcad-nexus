# ADR-0009: Contrato `TopologyProvider` versionado (Gyroid real, Voronoi preparado)

- Status: Aceita
- Data: 2026-07-30 (Incremento 2.2 Alpha Pesquisa)
- Decisor: Adler Lima Botelho de Azevedo (usuário) — instrução explícita: "crie uma abstração
  versionada e explícita; registre GyroidTopologyProvider como primeira implementação real;
  ... não implemente Voronoi completo ainda".

## Contexto

Até este incremento, o worker C# (`Program.cs`) despachava geometria com um único `if
(job.Recipe.Topology.Kind != "gyroid") throw new NotSupportedException(...)` -- qualquer
topologia futura exigiria editar diretamente o fluxo principal do worker. O backend Python não
tinha nenhum registro equivalente: a única barreira contra `topology.kind` desconhecido era o
JSON Schema (`"const": "gyroid"`).

## Decisão

1. **Duas abstrações espelhadas, mantidas em sincronia manual**:
   - Python: `apps/api/src/biomatcad_api/services/topology_providers.py` --
     `TopologyProviderInfo(kind, provider_class, version, status)`, `get_topology_provider(kind)`
     levanta `UnknownTopologyProviderError` para qualquer kind não registrado OU com
     `status="planned"`.
   - C#: `ITopologyProvider` (Kind, ProviderVersion, BuildAndExport) +
     `TopologyProviderRegistry` (`Dictionary<string, ITopologyProvider>`, sem descoberta
     automática por reflection).
2. **Gyroid é a única implementação real** (`status="implemented"` / `GyroidTopologyProvider`
   delega para `GyroidScaffoldBuilder.BuildAndExport` já existente, sem alterar nenhuma
   matemática de geração -- mesmo comportamento das 3 golden recipes já aprovadas).
3. **Voronoi aparece registrado com `status="planned"`** em ambos os lados -- deliberadamente
   rejeitado por `get_topology_provider`/`TryGet` até ter uma implementação real. A preparação
   técnica (sem código) está em `docs/architecture/voronoi-topology-preparation.md`.
4. **Defesa em profundidade no backend**: `create_design_run_and_job` rejeita
   (`reason_code=TOPOLOGY_PROVIDER_UNKNOWN`, HTTP 403) qualquer receita cujo `topology.kind` não
   seja um provider implementado -- mesmo que o JSON Schema já bloqueie isso na validação de
   entrada, esta é uma segunda camada que também alimenta o manifesto (`topology_provider`
   registrado explicitamente, nunca implícito).
5. **Sem carregamento dinâmico**: nenhuma implementação de `ITopologyProvider` é descoberta por
   reflection, assembly externo, plugin, ou qualquer mecanismo que aceite código enviado pelo
   navegador -- toda topologia suportada é uma classe C# compilada estaticamente neste mesmo
   assembly, revisada como qualquer outro código do worker.
6. **Schema JSON intocado nesta rodada**: `schemas/biomatcem/geometry-recipe-v1.schema.json`
   continua restringindo `topology.kind` a `"gyroid"` -- as 3 golden recipes existentes não
   sofrem nenhuma alteração de validação ou de checksum.

## Consequências

- Adicionar uma topologia futura (Voronoi ou outra) exige, no mínimo: uma nova versão do JSON
  Schema aceitando o novo `kind`, uma nova entrada `status="implemented"` no registro Python, uma
  nova classe `ITopologyProvider` registrada em `TopologyProviderRegistry` no C#, e testes
  equivalentes aos já escritos para Gyroid nos dois lados -- nunca uma mudança no fluxo de
  criação de projeto/receita/job/artefato/visualização.
- O tipo de retorno `GyroidScaffoldBuilder.BuildResult`, reaproveitado pela interface
  `ITopologyProvider.BuildAndExport`, é uma simplificação conhecida desta rodada (nomeado após
  Gyroid por ser a única implementação real hoje) -- pode precisar de generalização quando um
  segundo provider real for implementado; documentado aqui para não ser confundido com uma
  decisão de arquitetura definitiva.
- Testes do registro C# (`TryGet`/`Kind`/`ProviderVersion`/`KnownKinds`) exigiram um projeto de
  teste xUnit SEPARADO
  (`apps/geometry-worker/tests/BioMatCadGeometryWorker.TopologyProviderTests`) com
  `ProjectReference` ao projeto principal, diferente do projeto de testes PicoGK-livre já
  existente (`BioMatCadGeometryWorker.Tests`) -- necessário porque `ITopologyProvider` expõe
  `GyroidScaffoldBuilder.BuildResult` na assinatura. Confirmado empiricamente (antes de escrever
  os testes finais) que carregar o assembly principal e chamar apenas `TryGet`/`Kind`/
  `ProviderVersion` funciona neste sandbox sem o runtime nativo do PicoGK (indisponível em
  linux-x64, ver ADR-0007), pois o CLR resolve/JITa tipos e métodos sob demanda -- o método
  `BuildAndExport` nunca é chamado por estes testes.
