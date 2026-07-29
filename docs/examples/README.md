# Exemplos de entrega — STL e manifesto (Incremento 2.1)

Estes dois arquivos demonstram o FORMATO real de saída da vertical geométrica — não são
alegação de execução real do PicoGK (bloqueado neste ambiente, ver ADR-0007):

- `../../data/demo/geometry-examples/example-scaffold.stl` — o mesmo STL sintético pequeno (16.884 bytes, 336 triângulos) usado
  pelo modo demo do frontend, com cabeçalho binário rotulado explicitamente como não gerado
  pelo PicoGK.
- `example-manifest.json` — gerado por código de produção REAL
  (`services/manifest_service.py::build_and_store_manifest`), a partir de uma receita golden
  (`schemas/biomatcem/golden-recipes/block-gyroid-v1.json`) validada e canonicalizada pelo
  serviço real (`services/recipe_service.py`), e de um job persistido/transicionado pelo
  orquestrador real (`services/geometry_job_service.py`). O único componente substituído por um
  test double foi a chamada ao worker C#/PicoGK em si (bloqueado) — por isso
  `worker_version` aparece como `"0.1.0-example-for-delivery"`, não uma versão real do worker.
  `recipe_checksum_sha256` e `manifest_sha256` (calculado sobre este JSON, não incluído no
  próprio arquivo) são checksums reais, calculados por `hashlib.sha256`.

Em outras palavras: o *envelope* de reprodutibilidade (estrutura, campos, checksums, versões,
git commit, hardware) é real e testado; a *geometria* dentro dele (métricas, STL) é sintética
porque o worker real não pôde ser executado nesta sessão.
