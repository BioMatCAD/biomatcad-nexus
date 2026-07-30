# Identidade visual oficial — origem, autoria e situação de licença

## Arquivo-fonte

- `apps/web/public/brand/biomatcad-nexus-logo-original.png` — arquivo original fornecido pelo
  usuário na conversa (nome de upload original: `ChatGPT Image 28 de jul. de 2026, 00_15_29.png`),
  preservado aqui **byte a byte, sem qualquer alteração** (SHA-256 confirmado idêntico ao arquivo
  enviado: `45016352df9caa513502734cc98fd3d49d07b70042d44881a579dca944271daf`).
- Dimensões originais: 1914×822 px, RGB, fundo quase branco (~`#fefefe`).
- O nome do arquivo ("ChatGPT Image...") indica que a marca foi gerada com auxílio de uma
  ferramenta de geração de imagem por IA. **Autoria e situação de licença não foram formalmente
  registradas nesta rodada** — o usuário é o solicitante e proprietário do projeto BioMatCAD
  Nexus, mas nenhuma declaração de titularidade de direitos autorais sobre a marca em si foi
  feita explicitamente até este ponto. Isto fica registrado aqui como pendência para definição
  futura de estratégia de propriedade intelectual, junto com o restante do material do projeto.
- **Não é usada, e não deve ser usada, a marca ® ou ™** em nenhum lugar do produto, documentação
  ou GitHub Pages, enquanto não houver decisão formal e, se aplicável, registro real junto ao
  INPI ou órgão equivalente. Nenhuma declaração de "marca registrada" é feita.

## Derivados gerados nesta rodada (todos a partir do arquivo original, sem redesenho)

Todos os derivados abaixo foram produzidos por operações determinísticas e não-destrutivas sobre
os pixels do arquivo original (recorte, remoção de fundo por preenchimento por inundação a
partir da borda, redimensionamento) — nenhuma cor, proporção interna, traço ou elemento gráfico
da marca foi redesenhado, distorcido ou alterado.

| Arquivo | Descrição | Técnica |
|---|---|---|
| `biomatcad-nexus-logo-original.png` | Arquivo-fonte, íntegro | nenhuma (cópia byte a byte) |
| `biomatcad-nexus-logo-horizontal-transparent.png` | Versão horizontal (símbolo + wordmark) com fundo removido | preenchimento por inundação (flood fill) a partir da borda da imagem, restrito a pixels quase-brancos/baixa saturação — preserva os "poros" brancos internos do símbolo (não conectados à borda) como opacos |
| `biomatcad-nexus-logo-horizontal-web-960.png` / `-web-480.png` | Versões redimensionadas para uso em cabeçalho/sidebar, mesma técnica de transparência | redimensionamento Lanczos a partir da versão transparente em resolução total |
| `biomatcad-nexus-symbol-transparent.png` | Símbolo isolado (hexágono), sem o wordmark | recorte da bounding box do símbolo na versão transparente (mesma técnica de remoção de fundo) |
| `favicon-16.png` / `favicon-32.png` / `favicon-48.png` | Favicons | redimensionamento do símbolo isolado, com preenchimento transparente até ficar quadrado |
| `apple-touch-icon-180.png` | Ícone para dispositivos Apple | idem, 180×180 |
| `pwa-icon-192.png` / `pwa-icon-512.png` | Ícones para instalação como PWA (`manifest.json`) | idem, 192×192 e 512×512 |

## Verificação real da remoção de fundo (não assumida)

A primeira tentativa de remoção de fundo (limiar simples de brilho/saturação, sem considerar
conectividade) removia incorretamente os "poros" brancos internos do símbolo (parte real do
desenho, não do fundo da página) — confirmado numericamente pela amostragem de pixels dentro dos
poros, que mostrava alfa=0 onde deveria ser opaco. Corrigido usando rotulagem de componentes
conectados (`scipy.ndimage.label`), removendo como fundo **apenas** a(s) componente(s) de pixels
quase-brancos que efetivamente tocam a borda da imagem (exatamente 1 de 28 componentes de fundo
detectadas toca a borda) — os demais "poros" internos permanecem opacos, exatamente como no
arquivo original. Reverificado por amostragem de pixel nos mesmos pontos após a correção.

## Pendência registrada honestamente: contraste no tema escuro

O símbolo contém um segmento hexagonal em azul-marinho muito escuro (cor mais escura amostrada:
RGB ≈ (0, 4, 36)). O contraste calculado (fórmula WCAG de luminância relativa) entre esta cor e
o fundo do tema escuro do produto (`--color-bg: #10181a`) é de **apenas 1,12:1** — muito abaixo
do mínimo recomendado (3:1 para elementos gráficos).

Não foi fabricada nenhuma versão recolorida ou com contorno para "corrigir" isso — alterar as
cores ou adicionar um contorno seria redesenhar a marca, o que foi explicitamente pedido para
evitar ("não redesenhe a marca, não distorça proporções"). Também não foi usado um retângulo
branco atrás do símbolo no tema escuro (evitar fundo branco retangular no tema escuro é um
requisito explícito). O símbolo transparente é usado tal como é, em ambos os temas — os
segmentos ciano/turquesa/roxo permanecem bem visíveis em qualquer fundo (contraste 5,4:1 a
8,8:1 contra o fundo escuro), mas o segmento azul-marinho fica pouco visível em tema escuro.
**Esta é uma decisão de design pendente para uma futura revisão com quem detém a autoria da
marca — registrada aqui, não resolvida por fabricação.**

## Onde a marca é usada nesta rodada

- Landing page (`LandingPage.tsx`): logo horizontal acima do título, link para "Sobre o projeto".
- Tela de login (`LoginPage.tsx`): logo horizontal no topo do cartão.
- Cabeçalho autenticado (`TopBar.tsx`): símbolo isolado + texto "BioMatCAD Nexus" (antes era só
  texto solto).
- Barra lateral (`Sidebar.tsx`): símbolo isolado no topo da navegação + link para a página Sobre.
- Página "Sobre" (`AboutPage.tsx`, nova, rota pública `/about`): logo horizontal + resumo desta
  mesma nota de proveniência.
- `index.html`: favicon (16/32/48px), `apple-touch-icon`, `manifest.json` referenciando os
  ícones PWA — todos usando o placeholder `%BASE_URL%` do Vite, para funcionar corretamente
  tanto no build normal (`base: "/"`) quanto no build de demonstração do GitHub Pages
  (`base: "/biomatcad-nexus/"`, ver `vite.config.ts`).
- `apps/web/public/manifest.json`: caminhos dos ícones são relativos (`brand/pwa-icon-192.png`,
  sem barra inicial) — resolvidos pelo navegador relativamente à própria URL do manifesto, que
  já está sob o `base` correto em qualquer um dos dois builds.
- GitHub Pages (build de demo): os mesmos arquivos de `apps/web/public/brand/` e
  `apps/web/public/manifest.json` são copiados para `dist/` pelo próprio Vite (comportamento
  padrão para a pasta `public/`); verificado de fato inspecionando `dist/index.html` e
  `dist/brand/` após rodar `npm run build` e `npm run build:pages` (ver commit desta rodada).

## Texto alternativo (acessibilidade)

Todo uso de imagem da marca inclui `alt` descritivo (nunca `alt=""` decorativo, já que a marca
carrega identidade, não é puramente decorativa): a variante horizontal usa
`alt="BioMatCAD Nexus"`; o símbolo isolado usa `alt="Símbolo BioMatCAD Nexus"`.

## Peso dos arquivos (otimização sem degradação perceptível)

Todas as versões PNG usam o passo de otimização sem perda do Pillow (`optimize=True`); as
versões redimensionadas para uso em cabeçalho/sidebar (`-web-480`, `-web-960`) evitam carregar a
imagem em resolução total (1914×822, ~815KB) onde ela será exibida em poucas dezenas de pixels
de altura.

## Base64 no código

Nenhuma imagem é incorporada como Base64 em nenhum arquivo de código-fonte — todos os arquivos
vivem em `apps/web/public/brand/` como arquivos PNG reais, referenciados por caminho via
`import.meta.env.BASE_URL` (ver `apps/web/src/components/brand/BrandLogo.tsx`).
