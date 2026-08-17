# Registro técnico

Diário de engenharia do projeto: decisões, achados, bugs e — principalmente —
**o que foi verificado e o que não foi**. Existe para dois usos concretos:

1. **Revisão final.** Ao reescrever a monografia com suas palavras, este arquivo
   diz de onde veio cada número e o que sustenta cada afirmação.
2. **Caça a bugs.** As seções "Erros de diagnóstico" e "Não verificado" são o
   ponto de partida: são as áreas onde algo ainda pode estar errado.

Convenção: cada sessão acrescenta uma seção datada. Nada é reescrito
retroativamente — correção posterior vira nota nova, não edição silenciosa.

---

## 2026-08-16 — Execução dos sete braços, SFT e figuras

### Estado ao fim da sessão

| | |
|---|---|
| Braços executados | 7 (A1, A1g, A2, A2g, A3, A3m, A4) — 1.113 gerações |
| Erros de geração | 0 |
| Testes | 291 passando, `ruff` limpo |
| Monografia | 91 páginas, compila sem erro nem referência indefinida |
| Figuras | 6 (5 quantitativas + 1 qualitativa), geradas de CSV |
| Custo do SFT | US$ 0,47 (A40 alugada, 1h01m) |

### Resultado das hipóteses

| | enunciado | desfecho |
|---|---|---|
| H1 | A2 ≥ A1 em DF-F1 | **refutada**, p_holm 0,039 |
| H1g | A2g ≥ A1g em DF-F1 | **refutada**, p_holm 0,005 |
| H2 | A2 > A1 em XSD-Val | **refutada**, 64,8% vs 98,1% |
| H3 | A4 ≥ A2 em DF-F1 | **não refutada, não demonstrada**, p_holm 0,25 |
| H4 | TCR ≥ 2 | **confirmada**, ≈ 7 |

**O achado de maior magnitude não corresponde a hipótese alguma**: validade
sintática do A4 em 86,8% contra 64,8% do A2. Um 7B finetunado emite DSL válida
com mais confiabilidade que um modelo de fronteira com a gramática no prompt.

### Auditoria de proveniência (verificada nesta sessão)

Consulta a `benchmark_eval` confirmou que todos os braços gravaram `prompt_sha256`
idêntico ao dos arquivos atuais:

| braço | prompt sha | arquivo |
|---|---|---|
| A1, A1g | `0dbf1e014ff2` | `xml_direct.md` |
| A2, A2g, A3 | `c6bb757ea9b1` | `dsl_grammar.md` (pós-emenda E-1) |
| A3m, A4 | `11eaf38e2435` | `dsl_minimal.md` |

**Consequência**: A2 e A2g usaram o prompt corrigido, e o A3 foi reexecutado com
ele. Não há mistura de versões de prompt entre braços comparados.

`spec_commit` difere entre braços porque foram executados em momentos distintos
— isso é proveniência correta, não inconsistência.

**Dois braços rodaram antes do conserto do `strip_fence`** (commit `cb5a468`):
A3m (`33e716e`) e A3 (`1eb061f`). Ambos verificados como não afetados:
- A3 teve **zero truncamentos**, então a cerca sem fechamento nunca ocorreu.
- A3m foi reprocessado com o conserto e permaneceu 0/53 — suas 53 saídas são
  BPMN XML, que não parseia como DSL com ou sem cerca.

### Bugs encontrados e corrigidos

| bug | como apareceu | efeito se não corrigido |
|---|---|---|
| `strip_fence` exigia cerca de fechamento | investigando o A3m (81 truncamentos) | penalizaria **o baseline** — braços de XML emitem mais cerca e chegam mais perto do teto; inflaria nosso resultado |
| `seq 1024` no plano de SFT | medição do orçamento de tokens antes de treinar | truncaria 98% dos exemplos **no alvo**; queda de validade seria atribuída ao método |
| `treino.json` salvava só as últimas 8 entradas | ao montar a curva de treino | histórico completo perdido junto com o pod (**aconteceu** — só os 3 `eval_loss` sobreviveram) |
| `uv sync` instala torch incompatível | primeiro setup no RunPod | `torch 2.11+cu130` contra driver CUDA 12.8; travaria qualquer máquina nova |
| Emenda E-1: bloco GATEWAYS sem glosa | análise das falhas do A3 | penalizava só os braços de DSL (handicap específico de formato) |

### Erros de diagnóstico que eu cometi — LEIA ANTES DE CAÇAR BUGS

Estes são o padrão de risco mais importante do projeto: **sondas escritas sem
verificar como a ferramenta realmente se comporta**, que devolvem números
plausíveis e errados. Todos foram pegos, mas o padrão pode ter sobrevivido em
lugares que não revisamos.

1. **Regex `and\s*\{` para detectar paralelismo.** A sintaxe real é
   `and "Nome" {`. Conclui, e afirmei, que o pipeline destruía paralelismo
   (1,8% de cobertura). O valor correto é **35%**. Construí um diagnóstico
   inteiro sobre isso antes de descobrir.
2. **`_node_multiset` devolve categorias, não rótulos.** Medi "97% de
   alinhamento de rótulos" que na verdade alinhava `{task, event}` com
   `{task, event}` — trivialmente verdadeiro.
3. **`align_labels` devolve `candidato → referência`.** Consultei `g in al` em
   vez de `g in al.values()`, e rótulos com Jaccard 1,0 apareceram como não
   alinhados. Quase reportei bug inexistente na métrica.
4. **`.*` guloso em regex de log.** Numa linha com dois dicionários de eval,
   casava do primeiro ao último e devolvia uma ocorrência só. Me fez concluir
   que a avaliação da época 2 não tinha rodado.
5. **Monitor sem tratar `\r` do tqdm.** Reportou a mesma linha três vezes e me
   fez suspeitar de travamento inexistente no treino.
6. **Figura calculando DF-F1 sem tratar XML malformado.** As gerações truncadas
   do A1 saíam da média em vez de entrar como zero; A1 aparecia com 0,2070 na
   figura contra 0,1942 na tabela. Só apareceu porque exigi igualdade exata.

**Regra que tiro disso**: quando uma sonda nova produzir um número que sustenta
uma conclusão forte, verificar a sonda contra o código de produção antes de
acreditar nela. Nos casos 1, 2 e 6 o número era plausível e estava errado.

### Achados que mudaram o entendimento do projeto

#### 1. Teto humano da métrica — o mais importante

As 172 referências alternativas do Zenodo cobrem 24 itens com 4 a 11 modelos do
**mesmo** processo. Comparando-as entre si com a régua idêntica à dos braços
(regra do máximo, duplicatas exatas descartadas):

| limiar Jaccard | teto humano | A1 | oráculo do pipeline |
|---|---|---|---|
| 0,50 (congelado) | **0,1449** | 0,1942 (134%) | 0,1533 (106%) |
| 0,01 (estrutura pura) | **0,2734** | 0,3940 (144%) | 0,3419 (125%) |

Alinhamento de rótulos: humano vs humano **31,0%**; nosso pipeline **32,3%**.

**Consequência**: DF-F1 contra referência única satura perto do ruído. Todos os
métodos operam na vizinhança do teto humano, e os braços de XML o ultrapassam.
Isso invalida qualquer plano de "melhorar a topologia" — não há folga
verificável, e otimizar acima disso é ajustar às idiossincrasias de um modelador.

**Caveat**: teto estimado sobre 24 itens, não 53. Assume que as alternativas do
Zenodo são modelos independentes de especialistas — inferido do CLAUDE.md, **não
verificado na fonte original (Mangler et al. 2023)**.

#### 2. Oito itens estruturalmente inatingíveis

8 de 53 itens dão DF-F1 zero em **todos** os sete braços, inclusive nos de XML
direto. As referências não são degeneradas (4 a 73 arestas). A causa é convenção
de nomenclatura: esses golds escrevem orações em 3ª pessoa com ator por sujeito
(`MPOO confirmes the dismissal`), e o protocolo instrui forma imperativa
(`Confirm Dismissal`). Sem radicalização morfológica, `checks` nunca casa com
`check`.

Rótulos desses itens: **5,22 palavras** contra 3,47 nos demais.

Excluindo-os: A1 0,1942→0,2287, A2 0,1375→0,1619, A4 0,1114→0,1312. Cerca de 18%
em todos, **ordenação inalterada**.

**Não é defeito da DSL** — o A1 gera XML puro e zera nos mesmos itens.

#### 3. O oráculo: teto imposto pelos dados de treino

A DSL do próprio pipeline para os 53 itens, pontuada contra o gold com a regra do
máximo, dá **0,1533**. É o teto do SFT: um modelo que aprendesse o treino com
perfeição não passaria disso.

Três causas foram investigadas e **descartadas**:

| hipótese | medição | veredito |
|---|---|---|
| conversor perde paralelismo | JSON 68% → DSL 66% | falso |
| rótulos derivam do texto por 2 saltos de LLM | ancoragem 62,1% (gold: 60,8%) | falso — somos os mais ancorados |
| estrutura subdimensionada | 14 arestas vs gold 18; A1 tem 12 | falso — somos os mais próximos |

Resta escolha lexical, que está no nível da variação humana. **Não há defeito a
corrigir no pipeline de dados.**

#### 4. A memória de logits domina o treino, não os pesos

Vocabulário do Qwen2.5 tem ~152k. A seq 4096, a matriz de logits em fp32 passa de
2,5 GB — é ela que impede treinar na 2080 Ti (10,6 GiB), não o tamanho do modelo.

Corolário medido: **batch maior é pior**. Batch 2 ficou 42% mais lento que batch 1
(395,7s vs 278,4s para o mesmo trabalho), por desperdício de padding — os
exemplos variam de ~500 a 4096 tokens. Batch 4 estoura 44 GiB.

#### 5. Split agrupado mudou o modelo entregue

`eval_loss`: 0,4402 (ép. 1) → **0,4160** (ép. 2) → 0,4216 (ép. 3). O
`load_best_model_at_end` selecionou a época 2. Verificado por sha256 que o
adapter salvo é idêntico ao `checkpoint-168`.

Sem o critério de parada por validação **agrupada por documento**, teríamos
entregue um modelo levemente sobreajustado.

### Decisões tomadas e o porquê

| decisão | razão |
|---|---|
| Não atacar topologia | melhoria seria **inverificável** — estamos a 125% do teto humano estrutural |
| Não fazer scraping | o teto é da métrica, não dos dados |
| Não mexer no limiar de Jaccard | afrouxá-lo depois de ver números baixos elevaria todos os braços — o oposto do teste da emenda E-1 |
| GRPO fora do escopo | recompensa restrita é **explorável** (premia a menor DSL válida); e a folga em validade caiu de 41,5 para 13,2 pontos |
| A4 avaliado localmente, não no pod | a A40 usaria bf16 e o contraste A4-vs-A3 misturaria precisão numérica com efeito do adaptador |
| Adapter fora do git | 154 MB estoura o limite de 100 MB/arquivo do GitHub |

### Não verificado — candidatos a bug

Áreas onde afirmamos algo sem verificação independente completa:

1. **Independência das referências do Zenodo.** O teto humano assume que as 172
   alternativas são modelos independentes de especialistas. Veio do CLAUDE.md,
   não da leitura de Mangler et al. 2023. Se forem variantes derivadas umas das
   outras, o teto está **subestimado**.
2. **`pmo_18` sem diagnóstico.** Falha de parse no A3 cuja causa nunca foi
   identificada. Testei a hipótese de `#id` como step isolado e ela **parseia**
   normalmente — então a causa é outra.
3. **Heurística de "frase com ator"** pegou só 3 dos 8 itens que zeram. O
   mecanismo é mais amplo que a heurística; o sinal robusto é o comprimento do
   rótulo (5,22 vs 3,47).
4. **`rescore` repontua de `output_xml`, não de `raw_output`.** Não consegue
   reparar bugs na camada de parsing sem regerar. Se algum bug de parsing for
   descoberto depois, `--rescore` **não** o corrige.
5. **`mf_ref_size` não existe no banco.** O recorte de MF-F1 sobre itens com
   mensagem foi calculado ad hoc, não persistido.
6. **Ordenação instável entre subconjuntos.** Nos 53 itens A4 < A2; nos 24 com
   referência múltipla A4 > A2. Com n=53 e variância alta, diferenças pequenas
   não são confiáveis.

### Como reproduzir cada número

```bash
# descritivo por braço, contrastes pré-registrados, exploratórios
uv run python -m src.evaluation.run_analysis

# TCR e tokens emitidos por braço
uv run --with transformers python -m src.evaluation.run_tcr --all-arms

# CSVs das figuras (regenera tudo que as figuras leem)
uv run --with transformers python -m src.evaluation.export_figuras

# diagrama BPMN de qualquer item, em TikZ
uv run python -m src.evaluation.bpmn_tikz pmo_52 --arms A1,A2,A4

# dataset de SFT (690 treino / 78 validação, 232 grupos)
uv run python -m src.training.export_dataset

# treino (nuvem; ~1h em A40, US$ 0,47)
uv run python -m src.training.train_sft --smoke   # valida memória primeiro
uv run python -m src.training.train_sft
```

**Números que NÃO saem de comando** e foram calculados ad hoc nesta sessão —
candidatos a virar script se forem para a monografia:

- teto humano por limiar (está em `export_figuras.teto_humano`)
- oráculo do pipeline (0,1533)
- os 8 itens que zeram em todos os braços
- ancoragem de rótulos no texto-fonte (60,4% a 62,1%)
- comprimento de rótulo por braço (mediana 3,0 em todos)

---

## 2026-08-17 — Conclusão, pré-textuais e conferência bibliográfica

### Escrito nesta sessão

Conclusão (era `\lipsum`), Resumo, Abstract, Lista de Abreviaturas e Siglas,
Lista de Símbolos, subseção sobre o gerador determinístico de leiaute, e revisão
da Introdução. Monografia em 97 páginas, compilando sem erro nem referência
indefinida.

### Referência inexistente encontrada no `.bib` — LEIA ISTO

A entrada `volter2024generative` afirmava:

> V\"olter, Maximilian; Hake, Philip; Fettke, Peter. *Generative AI for Business
> Process Management: Suitability of Modalities*. Business Process Management
> Workshops, Springer, 2024.

**Esse artigo não existe.** O título corresponde à **apresentação de defesa de
mestrado de Marvin Völter na Universität Ulm** (abril de 2024). Hake e Fettke não
têm relação com o trabalho, e não há publicação Springer com esse título.

A fonte real da representação *Process Model Elements* é:

> Voelter, M.; Hadian, R.; Kampik, T.; Breitmayer, M.; Reichert, M.
> *Leveraging Generative AI for Extracting Process Models from Multimodal
> Documents*. arXiv:2406.04959, 2024.

Substituída por `voelter2024multimodal`, com a citação atualizada em
`trabalhos-relacionados.tex`.

**Origem do erro**: o cabeçalho do `.bib` já advertia que essas entradas foram
"preenchidas por conhecimento bibliográfico e não a partir do PDF original".
Preenchimento por memória produz entradas com aparência plausível — autores reais
da área, veículo plausível, ano plausível — e conteúdo falso. É a mesma classe de
risco das sondas descritas na seção anterior: **o resultado parece certo, e é
por isso que passa**.

**Regra que fica**: nenhuma entrada bibliográfica entra sem verificação contra
registro publicado. Entrada preenchida de memória deve ser marcada como tal até
ser conferida.

### Correção de autoria

`kopke2024efficient` trazia *Mohamed Safan*; a coautora é **Aya Safan**.
Confirmado por duas vias independentes: registro Springer e bibliografia do PDF
do PMo.

### Método da conferência, e seu limite

As atribuições das representações comparadas (*JSON branches* e *PME*) foram
resolvidas baixando o **PDF do próprio PMo** (arXiv:2507.11356) e lendo sua
bibliografia — fonte primária da atribuição, já que é o PMo quem compara essas
representações. `JSON branches` é a referência [10] do PMo; `PME` é a [19].

Demais entradas conferidas contra registro de editora e DOI. Acrescentados DOIs
a `zha2010tar`, `weidlich2011behavioral` e `dijkman2011similarity`, todas com
volume, número, páginas e autoria corretos.

**Limite**: a verificação usou registros publicados e a bibliografia do PMo, e
**não** a leitura integral de cada PDF. Não cobre errata, divergência de
paginação entre versão online e impressa, nem mudança de veículo posterior.

### Pendências de build

O documento agora exige a sequência completa, sob pena de a lista de siglas sair
vazia ou as referências desatualizadas:

```
pdflatex main && bibtex main && makeglossaries main && pdflatex main && pdflatex main
```

Vale automatizar com `latexmk` ou um alvo de Makefile.

### Diagnóstico errado desta sessão

Concluí que o arquivo de siglas nunca era carregado e acrescentei um `\input` no
preâmbulo — gerando 18 erros de "entry already defined". O `lib/unifortex2.sty`
**já o carrega** na linha 34. A causa real da lista vazia era outra: o texto usa
as siglas em forma literal, nunca via `\gls`, e sigla não referenciada não é
registrada como usada. A correção necessária era só `\glsaddall`.

Mesmo padrão de sempre: sintoma com duas explicações compatíveis, e escolhi a
errada antes de verificar qual delas o código sustentava.
