# Apresentação da defesa (HTML)

`apresentacao.html` (tema escuro) e `apresentacao-clara.html` (tema claro) são
arquivos únicos: abrem direto no navegador, sem servidor e sem internet (CSS, JS
e fontes estão embutidos). São 26 slides animados, iguais nos dois arquivos.
Se o projetor deixar o tema escuro ilegível, abra o claro (ou aperte `T`).

## Usar

Abra `apresentacao.html` ou `apresentacao-clara.html` no Chromium ou no Firefox
e aperte `F` (tela cheia).

| Tecla | Ação |
|---|---|
| `→`, espaço, PageDown, clique | avança um passo da animação |
| `←`, PageUp, clique direito | volta um passo |
| `↓` / `↑` | próximo slide / slide anterior |
| número + Enter | vai para o slide |
| `G` | índice dos slides |
| `R` | repete a animação do slide |
| `T` | troca o tema (não fica salvo: o arquivo reabre no próprio tema) |
| `B` | tela preta |
| `?` | ajuda |

Os pontinhos ao lado do número da página mostram quantos passos o slide tem.
Passar o mouse sobre um ponto das tiras de 138 gerações mostra o item, a
repetição e a causa da falha.

## Editar e regerar

```bash
# dados reais (banco + transpilador) -> src/js/data.js
uv run python internal_tests/apresentacao/dados.py
# junta src/ em apresentacao.html e apresentacao-clara.html
python internal_tests/apresentacao/build.py
```

- `src/js/slides-a.js` a `slides-e.js`: os slides, na ordem.
- `src/js/kit.js`: BPMN, código com realce, tiras de 138 pontos.
- `src/js/engine.js`: navegação e passos.
- `src/css/`: tema (`base.css`) e estilos de cada slide (`slides.css`).

## PDF para a banca

`apresentacao.pdf` (escuro) e `apresentacao-clara.pdf` (claro) têm os 26 slides
no estado final, sem animação. Para regerar depois de mudar a apresentação:

```bash
for f in apresentacao apresentacao-clara; do
  chromium --headless=new --no-pdf-header-footer --virtual-time-budget=15000 \
    --print-to-pdf=$f.pdf "file://$PWD/$f.html?print"
done
```

## De onde vêm os números

- Tiras de validade e causas de falha: `data/dataset.db`, tabela
  `benchmark_eval`, 46 itens. `dados.py` falha se as contagens deixarem de
  bater com as tabelas da monografia.
- XML do exemplo: gerado pelo transpilador do projeto a partir do Código 1.
- Demais valores (custo, compressão, fidelidade, validação do juiz): copiados
  das tabelas da monografia na versão de 14/11/2026, em `slides-*.js`.
  Se a monografia mudar, conferir esses arquivos.

## Não verificado

- As animações foram conferidas só pelo estado final de cada passo, em
  capturas de tela. Falta assistir à apresentação inteira em tempo real.
- O tema claro foi conferido em capturas dos 26 slides (estado final) e de um
  slide com animação em andamento; não foi assistido inteiro nem num projetor.
- O slide 26 (encerramento) não teve a captura revisada.
