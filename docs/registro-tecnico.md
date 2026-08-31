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

---

## 2026-08-23 — Declaração dos braços exploratórios (antes de executar)

Escrito **antes** de rodar qualquer treino novo. O valor de um pré-registro é
inteiramente a data: declarado depois de ver o resultado, não vale nada.

### Contexto: o orçamento decide o calendário

O pod da A40 ficou uma semana ligado sem uso e consumiu ~US$ 4 só de SSD
(~US$ 0,57/dia). Restam US$ 5. O treino do A4 custou US$ 0,47 (3.675 s, 252
passos, 14,6 s/passo). Como o saldo evapora em ~9 dias parado, a pergunta não é
"vale gastar?" — é "gastar agora ou perder".

Verificado antes de decidir: **o pod não guarda nada.** `experiments/sft/`
local tem adapter, tokenizer, `train.jsonl`, `val.jsonl`, `manifest.json` e
`treino.json`; a avaliação roda na 2080 Ti. O pod é aluguel de compute
descartável, não workspace.

### Dois braços exploratórios, declarados agora

Não integram os sete pré-registrados da spec 003 §4 e não entram em nenhum
contraste corrigido por Holm. Vivem no prefixo `X-` em `run_benchmark.ARMS`, e
dois testes guardam a separação (`test_arms_cobrem_os_bracos_do_spec`,
`test_exploratorios_ficam_fora_dos_contrastes_pre_registrados`).

- **`X-lc25` / `X-lc50` — curva de aprendizado.** Mede sobre **XSD-Val**, não
  DF-F1: a DF-F1 satura no ruído (teto humano 0,1449), então curva sobre ela
  sairia plana e não proveria nada; a validade tem folga real (86,8% contra
  100%). Os dois desfechos são publicáveis — saturou encerra a questão de
  volume, ainda sobe vira trabalho futuro com número.
- **`X-ds` — segunda família de modelo** (`deepseek-ai/deepseek-coder-6.7b-instruct`).
  **Risco declarado antes:** se não replicar, a alegação "um 7B especializado
  atinge X" enfraquece em vez de fortalecer. É por isso que vale medir.

### O ponto de 100% da curva é o A4 existente — não retreinar

Retreinar com 100% produziria outro adapter (o ADR 0003 já mostrou que
temperatura 0 não garante determinismo, e treino menos ainda), e os números do
A4 foram reportados sob protocolo congelado com o adapter atual. Trocá-lo
invalida resultado publicado para ganhar uma curva de perda.

Custo dessa escolha: o `treino.json` do A4 tem só 8 entradas de histórico,
começando no passo 200 — resíduo do bug `[-8:]`, corrigido no script **depois**
desse treino. Não há curva de perda do A4, e não haverá. Os runs novos gravam
histórico completo, então a curva terá pontos com histórico e um sem.

### Pré-voo local, para não depurar em GPU paga

Cada minuto de depuração no pod é pago e quase toda ela cabe em CPU. Feito antes
de subir:

- `src/training/subsample.py` — subamostras **por grupo** (documento de origem),
  não por exemplo: "mais dados" nesse corpus significa mais documentos, dado que
  95,3% do treino vem de um handbook só. Frações **aninhadas** (prefixo da ordem
  sha1), senão a curva mistura volume com composição. `val.jsonl` intocado.
  Resultado: 690 exemplos/207 grupos → lc25 173/51, lc50 350/96. Aninhamento e
  ausência de vazamento verificados por asserção no próprio script.
- `src/training/check_template.py` — reusa o `montar()` do treino para checar,
  **só com o tokenizador e sem pesos**, a invariante de prefixo exato em tokens
  e a taxa de descarte acima de 4096. Quatro candidatos passaram na invariante:

  | modelo | vocab | usados | descartados | mediana |
  |---|---|---|---|---|
  | Qwen2.5-Coder-7B-Instruct | 151.665 | 672 | 18 | 1.593 |
  | deepseek-coder-6.7b-instruct | 32.022 | 657 | 33 | 1.916 |
  | granite-8b-code-instruct-4k | 49.152 | 669 | 21 | 1.709 |
  | Mistral-7B-Instruct-v0.3 | 32.768 | 664 | 26 | 1.802 |

  DeepSeek escolhido por ser família de pré-treino distinta e code-instruct como
  o Qwen — isola *família*, não *tipo* de modelo. Descarte 33 contra 18 (4,8% vs
  2,6%): corpora comparáveis. Granite é reserva (Apache 2.0, descarte mais
  próximo), mas contexto de 4k não deixa folga sobre `seq 4096`.

### Estimativa da sessão do pod

14,6 s/passo, lote efetivo 8, 3 épocas: lc25 ≈ 15 min, lc50 ≈ 31 min, DeepSeek
≈ 72 min (sequências ~20% mais longas). ~2 h ≈ US$ 0,91, mais ~US$ 0,20 de
download e setup. **~US$ 1,10 dos US$ 5.** Regra de corte: se o DeepSeek não
estiver treinando em 45 min de pod, aborta — a curva já estará salva.

### Não verificado ainda

- Se `local_model.load` de fato roda o DeepSeek em 4-bit na 2080 Ti. A assinatura
  é parametrizada (`load(model_id, adapter)`) e o template passou, mas nenhum
  peso foi carregado. Falha aqui não custa dinheiro de GPU alugada — só refaz a
  avaliação local.
- **O bug do torch NÃO está corrigido no repo.** `pyproject.toml` mantém
  `torch>=2.4` sem pin, então `uv sync --extra training` numa máquina nova pode
  resolver de novo para `2.11+cu130` e não enxergar a GPU. O conserto de agosto
  foi ad hoc no pod e se perdeu com ele. Não pinei aqui porque a resolução atual
  funciona na 2080 Ti local e mexer nela arrisca o ambiente que avalia — o
  contorno vai no roteiro: conferir `nvidia-smi`, sincronizar, e **verificar
  `torch.cuda.is_available()` antes de treinar**, reinstalando do índice
  correspondente se der `False`. São 2 min de pod contra ~1 h de depuração paga.

### Resgate do pod antes de terminar (mesma data, sessão de CPU)

O pod perdeu a alocação de GPU e o RunPod ofereceu migrar / subir em CPU / nada.
Escolhida a CPU: é acesso barato ao disco. Migrar levaria junto o volume que
custa os US$ 0,57/dia, e já estava verificado que nada ali era insubstituível.
Rendeu mais do que se esperava.

**1. A curva de perda do A4 NÃO estava perdida.** A nota de 2026-08-16 diz que o
histórico foi "perdido junto com o pod". Está **errada**, e fica corrigida aqui
por nota nova, não por edição: o stdout tinha ido para `/workspace/sft.log`.
Resgatados para o repositório:

- `experiments/sft/sft_a4.log` (40 KB) — stdout completo do treino
- `experiments/sft/trainer_state_a4.json` (8 KB) — histórico estruturado, em
  precisão cheia: **25 perdas de treino (passos 10 a 250) e as 3 avaliações**

Perda de treino 1,1498 → 0,3347. `eval_loss` por época: **0,4402 → 0,4160 →
0,4216**.

**2. O modelo entregue é o da época 2, e agora está verificado.** O achado nº 5
("split agrupado mudou o modelo entregue") era inferência; virou fato por
checksum. O `adapter_model.safetensors` entregue tem md5 `93c43879...`, idêntico
ao de `checkpoint-168` (época 2) e **diferente** do de `checkpoint-252`
(`66d0f61f...`, época 3). Coerente com
`load_best_model_at_end=True` + `metric_for_best_model="eval_loss"` e com
`best_model_checkpoint: checkpoint-168` no `trainer_state`.

Consequência: **treinou 3 épocas, entrega a época 2** — a validação agrupada de
fato descartou a última época, que já estava piorando. Onde o texto disser "3
épocas" sem qualificar, falta essa precisão.

**3. Integridade do adapter local confirmada.** MD5 do `.safetensors` e do
`adapter_config.json` batem entre pod e máquina local. A cópia local é a
treinada, íntegra.

### Divergência entre metodologia e código — a conferir

`metodologia.tex` §"comprimento de sequência" afirma que os exemplos acima de
4.096 tokens ficaram "**truncados** de forma explícita e registrada". O código
faz o contrário: `montar()` os **descarta** (`continue  # descartar, não
truncar: alvo cortado ensina DSL inválida`), e `treino.json` registra
`n_treino: 672` = 690 − 18. Truncar e descartar não são a mesma decisão, e a que
está no texto é justamente a que o código rejeita por escrito. Corrigir na
revisão.

### O contorno do torch, agora escrito (pod novo, A40, mesma data)

O bug se repetiu exatamente como previsto e desta vez o conserto fica registrado.
`uv sync --extra training` resolve para **`torch 2.11.0+cu130`**, o driver do pod
é **CUDA 12.8**, e `torch.cuda.is_available()` devolve `False` com aviso de
"driver too old". Treinar nesse estado cairia para CPU ou falharia.

Não resolve: `UV_TORCH_BACKEND=cu128` (ignorado) nem `uv sync --torch-backend`
(flag inexistente no uv 0.9.0). **Resolve:**

```bash
uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu128
```

Resultado `torch 2.11.0+cu128`, `is_available() True`. Como só muda o build de
CUDA e não a versão, `triton 3.6.0`, `transformers 5.5.0` e `trl 1.0.0` seguem
compatíveis — evita o efeito colateral de rebaixar o torch.

Conferido na mesma sessão: `subsample.py` reproduziu no pod exatamente os
números da máquina local (lc25 173/51, lc50 350/96). O determinismo prometido no
docstring vale entre máquinas, não só entre execuções.

### Alterações no artigo decorrentes desta sessão

1. **Metodologia §comprimento de sequência** — corrigido "18 restantes truncados"
   para "**descartados**, e não truncados", com a razão explicitada: truncar
   incorreria no defeito que o próprio parágrafo acabara de descrever. Acrescido
   "Restam 672 exemplos de treino", que já era o número usado adiante.
2. **Metodologia §Infraestrutura e Reprodutibilidade** — acrescido o parágrafo
   sobre a compilação de PyTorch versus versão de CUDA do driver. Uma seção de
   reprodutibilidade que omite a única dependência capaz de interromper o
   treinamento em silêncio é boilerplate; com ela, é instrução.
3. **Figura 2 refeita** (`figuras/sft_eval.tex`) — agora dois painéis: perda de
   treino (25 pontos, recuperados hoje) e perda de validação (3 pontos). Escalas
   separadas porque respondem a perguntas diferentes: a primeira mostra que a
   otimização convergiu sem instabilidade, e portanto **não é ela que limita o
   resultado**; a segunda decide qual checkpoint virou modelo entregue.
4. **`export_figuras.py`** — a constante `EVAL_SFT`, com três valores digitados à
   mão, foi substituída por `historico_sft()`, que lê de
   `experiments/sft/trainer_state_a4.json`. O comentário do preâmbulo do artigo
   afirma que nenhum número de figura é transcrito manualmente; até hoje havia
   uma exceção, e ela existia só porque o histórico fora dado como perdido.

Compilação conferida: 97 páginas, sem erro, e a figura foi inspecionada
visualmente (página 66 do PDF) — compilar não prova que dois painéis não se
sobrepõem.

### Bug no transpilador: `#id` redeclarado gera `xs:ID` duplicado — ACHADO 2026-08-23

Descoberto ao conferir uma anomalia no `X-lc25`: `parse_ok` 88,7% contra
`xsd_valid` 86,8%. Três gerações **parseiam, transpilam e produzem XML que não
valida** — o que contradiz a garantia de validade por construção.

**Caso mínimo, determinístico:**

```
# OK   — declaração + referência nua
process "P" { start -> task "A" #a -> xor "Q" { [s] -> () [n] -> #a } -> end }

# FALHA — mesma #id em duas declarações completas
process "P" { start -> task "A" #a -> xor "Q" { [s] -> () [n] -> task "A" #a } -> end }
#   → Task_1 emitido duas vezes → 'Task_1' is not a valid value of the atomic type 'xs:ID'
```

O transpilador trata corretamente `declaração + #ref nu`, mas quando o mesmo
`#id` aparece numa **segunda declaração completa** ele emite um segundo elemento
com o mesmo identificador gerado.

**Por que 1021/1021 nunca pegou.** O corpus é produzido por `json_to_dsl`, que
sempre emite declaração-e-depois-referência-nua. 181 das 1021 DSLs têm `#ref`
repetido e todas validam — o gatilho não é o `#ref` repetido, é a **redeclaração**.
A garantia de XSD foi medida sobre a distribuição que o nosso próprio conversor
produz, **não sobre a que um modelo escreve**. Repetir o texto completo do nó é
mais natural para um LLM do que emitir referência nua.

**Alcance medido** (`parse_ok=1 AND xsd_valid=0`, todos os braços):

| braço | casos | itens |
|---|---|---|
| A2g | 3/159 (1,9%) | pmo_37 rep1, pmo_44 rep2 e rep3 |
| X-lc25 | 3/159 (1,9%) | pmo_45, as três repetições (saída idêntica) |

Nenhum outro braço. A4 tem `parse_ok == xsd_valid`, sem casos.

**A direção do viés exige cuidado redobrado.** Hoje essas gerações pontuam zero
em tudo, isto é, o defeito **penaliza os braços de DSL** — que são a hipótese
deste trabalho. Corrigir melhora o nosso próprio lado, e portanto é uma emenda
*favorável ao autor*, categoria que exige mais disciplina, não menos, do que a
do conserto do `strip_fence` (que penalizava o baseline).

Magnitude estimada: A2g sairia de 54,7% para ~56,6% de XSD-Val. **Nenhuma
ordenação muda, nenhuma conclusão muda.** É justamente por ser pequeno que dá
para corrigir e declarar sem constrangimento.

**`--rescore` NÃO conserta isso**, exatamente como o item 4 de "Não verificado"
antecipou: ele repontua a partir de `output_xml`, não de `raw_output`. Corrigir
exige **re-transpilar a partir do `raw_output`**, que está gravado.

**Decisão pendente** (do Rafael): consertar o transpilador + teste de regressão,
re-transpilar de `raw_output` e reportar antes/depois com divulgação explícita
da direção; ou manter como está e registrar a limitação. Não alterei nada.

### Correção aplicada, e a verificação que a torna confiável

**O conserto** (`src/transpiler/xml.py`): `add_node_element` passa a devolver o
elemento já emitido quando o `node_id` reaparece, em vez de criar um segundo.
`_id_for` já reusava o identificador; faltava não emitir o nó de novo. A primeira
declaração vence — rótulo e tipo dela permanecem, e o que a segunda acrescentaria
seria descartado de qualquer forma ao reusar o id.

**Prova de que a correção é inerte sobre o corpus** — o que importa num
componente que carrega a garantia da tese:

| verificação | resultado |
|---|---|
| Suíte de testes | 294 passando |
| Corpus re-transpilado | **1021/1021 byte-a-byte idênticos** ao materializado |
| XSD do corpus | 1021/1021 |
| Exceções | 0 |

Ou seja: a mudança não altera *nenhuma* saída que o corpus já produzia. Só afeta
a forma que ele nunca exercitou.

**Testes de regressão** (`tests/transpiler/test_xml.py`):
`test_transpile_redeclared_ref_emits_single_node` e
`test_transpile_redeclared_ref_is_xsd_valid`. Conferido que **falham sem a
correção** — teste de regressão que passa nos dois estados não testa nada.

**Os seis casos reais** foram re-transpilados de `raw_output` e agora validam:
A2g pmo_37 rep1, A2g pmo_44 rep2 e rep3, X-lc25 pmo_45 reps 1–3.

**`--retranspile`, novo** (`run_benchmark`): reconstrói `output_xml` a partir de
`raw_output` e repontua, sem chamar o modelo. Fecha o item 4 de "Não verificado":
`--rescore` sozinho parte de `output_xml` e não absorve conserto determinístico.
Regerar com o modelo para incorporar um conserto trocaria a saída avaliada;
re-transpilar mantém a geração intacta e refaz só a parte determinística.

**Ainda não executado** sobre o banco: a avaliação dos braços exploratórios está
gravando em `benchmark_eval` e rodar em cima disso é pedir contenção de escrita.
Aplicar quando a cadeia fechar, em **todos** os braços, e reportar antes/depois.

### Figuras com números digitados à mão — ACHADO, e pior que o bug

Ao mapear o que a correção do transpilador mexeria no artigo, descobri que
**três das seis figuras tinham as coordenadas escritas à mão**, apesar de os
CSVs existirem e de o preâmbulo (`lib/preambulo.tex`) afirmar: *"Nenhum número
das figuras é transcrito à mão: reexecutar um braço e rodar o script regenera
tudo."* A afirmação era falsa para `validade.tex`, `custo.tex` e
`df_f1_teto.tex`. Só `limiar.tex` lia dados de fato.

**A consequência já tinha se materializado.** O `validade.csv` gerado registrava
`A2g parse=56.6, xsd=54.7` — isto é, **o dado já continha a prova de que o
invariante estava quebrado**. E a nota da própria figura afirmava: *"Nos braços
de DSL a validade XSD coincide com a taxa de parsing, pois a transpilação é
determinística e sempre produz XML válido a partir de DSL aceita."* A evidência
contrária estava no arquivo que a figura deveria estar lendo, e ninguém cruzou.

**Conserto**: `export_figuras` passa a emitir também um CSV por série
(`{base}_{xml,dsl,sft}.csv`), e as três figuras leem por `\addplot table`. Um
arquivo por série em vez de filtro de tabela porque filtrar sob coordenada
simbólica é receita frágil no pgfplots. Conferido visualmente que as três
renderizam **valores idênticos** aos das versões escritas à mão.

### Mapa de impacto no artigo (a aplicar junto com o `--retranspile`)

Números afetados: apenas A2g (XSD 54,7% → 56,6%) e X-lc25 (86,8% → 88,7%).

| local | o que muda |
|---|---|
| `figuras/dados/*.csv` | regenerados por `export_figuras` |
| `figuras/{validade,custo,df_f1_teto}.tex` | nada — agora leem CSV |
| `resultados.tex:142` | linha do A2g na tabela principal |
| `introducao.tex:16` | "64,8\% e 54,7\%" |
| `conclusao.tex:6` | "64,8\% e 54,7\%" |
| Resumo / Abstract | **nada** — citam só A2 (64,8%) e A1 (98,1%) |
| Nota da `validade.tex` | reconferir: só vale se parse == xsd em todos os braços de DSL |

**Cuidado com a DF-F1 do A2g.** A prévia que rodei calculou média simples sobre
as 159 linhas (0,0855 → 0,0858), mas a tabela principal usa **média das medianas
por item** (0,0773). São estatísticas diferentes; não transcrever um número da
prévia para a tabela. Recalcular com `per_item_medians`, que é o caminho de
produção — exatamente o erro de "sonda ≠ produção" que este registro já
documenta três vezes.

### Investigação do "7/7/7": não é artefato, e o mecanismo é único

O Rafael desconfiou de os três braços ajustados falharem em exatamente 7 itens
cada, em itens diferentes. A desconfiança estava certa em exigir investigação, e
errada quanto a haver artefato. O que a investigação achou vale mais que a
resposta à pergunta original.

**1. Decomposição por causa mostra que o ajuste fino muda a NATUREZA da falha,
não só a quantidade.**

| braço | falhas de parse | causa dominante |
|---|---|---|
| A3m (Qwen, sem ajuste, prompt mínimo) | 159 | `UnexpectedCharacters` **100%** |
| A3 (Qwen, sem ajuste, gramática no prompt) | 66 | `UnexpectedCharacters` **100%** |
| A2 (DeepSeek fronteira) | 56 | 50% caracteres, 50% ref pendente |
| A2g (GLM fronteira) | 69 | 67% caracteres, 32% ref pendente |
| A4 (ajustado, 100%) | 21 | **ref pendente 71%**, EOF 29% |
| X-lc50 (ajustado, 50%) | 21 | **ref pendente 100%** |

Sem ajuste, o modelo pequeno **não escreve a notação** — falha léxica pura, zero
falhas de referência. Com ajuste, a sintaxe está correta e o que quebra é a
**contabilidade de referência cruzada**.

**2. As formas de referência pendente separam-se 100% por tipo de braço.**

| braço | refs pendentes | alvo opaco `tNN` | alvo tipo rótulo |
|---|---|---|---|
| A2 | 28 | **0** | **28** (`#stockCheck`, `#review`, `#build`) |
| A2g | 22 | **0** | **22** |
| A4 | 15 | **15** | 0 |
| X-lc25 | 9 | **9** | 0 |
| X-lc50 | 21 | **21** | 0 |

Modelos de fronteira instruídos por prompt **inventam nomes semânticos** de
referência que não casam com rótulo nem com declaração. Modelos ajustados usam
exclusivamente a convenção `tNN` do corpus — evidência direta de que o ajuste
transferiu a notação — e falham só em declarar antes de referenciar.

**3. O teste que refuta o artefato.** A hipótese natural era que só ~7 itens do
holdout precisassem de referência, o que faria do 7 um teto e não um resultado:

| braço | itens que emitem `#ref` | falhas | taxa condicional | falhas **sem** ref |
|---|---|---|---|---|
| A4 | 45 | 7 | 15,6% | **0** |
| X-lc25 | 38 | 7 | 18,4% | **0** |
| X-lc50 | 49 | 7 | 14,3% | **0** |

Refutada: 38 a 49 itens usam referência, com folga para falhar mais. Os
denominadores **diferem** entre braços; o 7 idêntico sai de taxas próximas
(média 16,1%) sobre bases diferentes. Coincidência de contagem, não de causa.

**4. O achado que importa: 100% das falhas dos braços ajustados são
referenciais.** Nenhuma falha em item sem `#ref` — zero, nos três braços. E em
39 dos 45 casos o id pendente aparece **uma única vez** na saída: é referenciado
e nunca declarado em lugar nenhum.

**Responde à pergunta do Rafael** — como o modelo de 100% erra o que o de 25%
acerta: a falha não é déficit de conhecimento, é um deslize estocástico de ~16%
por item sobre uma construção específica. Modelos diferentes deslizam em itens
diferentes. Não há "itens impossíveis": só 1 item (`pmo_46`) falha nos três.

**Explica a saturação da curva.** Mais dados não corrigem contabilidade de
referência cruzada, que exige manter estado ao longo de uma saída longa. É
limite de capacidade sob essa notação, não de volume de treino — coerente com a
curva plana em 86,8% para 51, 96 e 207 documentos.

**Implicação de projeto, para trabalho futuro.** A separação
declaração-versus-referência é o que cria o modo de falha. O `resolve_ref` já
resolve por **slug do rótulo** (`#nome_do_no`), caminho pelo qual 23 refs do
corpus resolvem sem declaração alguma. Uma notação que referenciasse nós pelo
rótulo já emitido eliminaria a contabilidade — e com ela, pela medição acima,
**a totalidade das falhas residuais dos braços ajustados**.

### O braço X-ds é INVÁLIDO — tokenizador do DeepSeek destrói espaços

**Não reportar nenhum número do X-ds.** As 159 linhas ficam no banco como
evidência, mas o braço não mede o que se propôs a medir.

**Sintoma**: `X-ds` fechou com 75,5% de validade XSD e **DF-F1 exatamente
0,0000 em 159 de 159**. Validade alta com fidelidade nula não é resultado
plausível; é sintoma.

**Causa**: sob `transformers` 5.5.0, `deepseek-ai/deepseek-coder-6.7b-instruct`
carrega como `LlamaTokenizer` e **descarta os espaços na codificação**:

```
entrada : start "Collect relevant information"
tokens  : ['start', '"', 'Collect', 're', 'levant', 'information', '"']
decode  : start"Collectrelevantinformation"
```

A perda é no *encode*, não no decode — `clean_up_tokenization_spaces=False` não
resolve, nem `use_fast=False`, nem `trust_remote_code=True`. A DSL resultante
ainda parseia e ainda gera XML **válido** (daí os 75,5%), mas todo rótulo vira
uma palavra concatenada, nenhum casa com a referência, e a DF-F1 zera.

Consequência dupla: **o treino também foi corrompido**, porque `montar()` usa o
mesmo tokenizador. O adaptador aprendeu DSL sem espaços. Não é conserto de
avaliação — exige retreinar.

**Round-trip dos candidatos** (`decode(encode(t)) == t`):

| modelo | classe carregada | round-trip |
|---|---|---|
| Qwen2.5-Coder-7B-Instruct | `Qwen2Tokenizer` | **OK** |
| deepseek-coder-6.7b-instruct | `LlamaTokenizer` | **QUEBRA** |
| granite-8b-code-instruct-4k | `GPT2Tokenizer` | **OK** |
| Mistral-7B-Instruct-v0.3 | `TokenizersBackend` | **OK** |

O DeepSeek é o único que quebra. Granite era a reserva declarada no pré-voo e
segue viável (Apache 2.0).

**Meu erro, e é o mais caro da sessão.** O `check_template.py` que escrevi
verificava a invariante de **prefixo exato em ids** — que continua satisfeita
quando prompt e alvo são igualmente destruídos, porque a destruição é uniforme.
Nunca verifiquei que o tokenizador devolve o texto que recebeu. Passei confiança
sobre a verificação errada, que é pior do que não verificar: escolhi o DeepSeek
*justamente* por ele ter "passado no pré-voo".

Custo: um treino de US$ 0,47, ~50 min de avaliação local, e quase um resultado
falso publicado ("o método não replica em outra família").

**Conserto aplicado**: `check_template.py` passa a testar ida-e-volta **antes**
de qualquer outra checagem, e reprova o candidato de imediato. Conferido que o
DeepSeek agora é rejeitado e os outros três passam.

**Padrão que isto confirma** (já são sete ocorrências neste registro): sonda que
verifica a invariante errada devolve verde e produz confiança. A regra do
registro dizia "verificar a sonda contra o código de produção"; falta acrescentar
— **verificar que a invariante testada é a que importa**.

### Braços de replicação declarados — 2026-08-23, ANTES de rodar

Substituem o `X-ds`, invalidado pelo tokenizador do DeepSeek. Pergunta: os 86,8%
de validade do A4 são propriedade do método ou do Qwen?

| braço | modelo | organização | arquitetura | contexto | vocab | descarte |
|---|---|---|---|---|---|---|
| A4 (base) | Qwen2.5-Coder-7B-Instruct | Alibaba | `Qwen2ForCausalLM` | 32.768 | 151.665 | 18/690 |
| `X-gr` | granite-4.1-8b | IBM | `GraniteForCausalLM` | 131.072 | 100.352 | 20/690 |
| `X-mi` | MiMo-7B-RL | Xiaomi | `MiMoForCausalLM` | 32.768 | 151.680 | — |
| `X-ms` | Mistral-7B-Instruct-v0.3 | Mistral AI | `MistralForCausalLM` | 32.768 | 32.768 | 26/690 |

**COMPROMISSO REGISTRADO ANTES DA EXECUÇÃO: todo braço que treinar entra no
texto, replique ou não.** Treinar três e reportar o melhor seria escolha a
posteriori — exatamente o vício que o pré-registro existe para impedir.

**Ornith-1.5-9B foi avaliado e descartado**, por dois motivos independentes:

1. **É derivado do Qwen.** O model card diz: *"Ornith-1.5 extends Ornith-1.0
   (which was developed **on top of Qwen3.5** and Gemma4...)"*. Replicar num
   modelo construído sobre Qwen não responde a pergunta do braço.
2. **Não é a arquitetura que treinamos.** `Qwen3_5ForConditionalGeneration` com
   `vision_config`, `image_token_id` e `video_token_id` — multimodal. O caminho
   é `AutoModelForCausalLM`, e o LoRA `all-linear` alcançaria camadas de visão.

Ser mais atual e mais forte em código é verdade e é irrelevante: o braço mede
linhagem, não capacidade.

**`X-mi` passa por portão.** MiMo tem `auto_map` (exige `trust_remote_code`) e
`num_nextn_predict_layers` (multi-token prediction), cuja interação com LoRA
`all-linear` é desconhecida. Regra fixada **antes**: se o `--smoke` falhar,
treina-se `X-ms` no lugar e **não se depura arquitetura em GPU alugada**. Se o
MiMo passar, `X-ms` não roda.

A ambiguidade das duas escolhas é de naturezas diferentes, e por isso a regra:
se o Mistral for mal, discute-se capacidade de um modelo geral de 2024 — uma
limitação que se escreve. Se o MiMo for mal, não se separa "o método não
transfere" de "o `all-linear` interagiu mal com as camadas de MTP" — isso não é
achado, é defeito.

**`trust_remote_code` virou campo do `Arm`**, desligado por padrão, com teste
(`test_trust_remote_code_e_desligado_salvo_declaracao_explicita`) fixando que só
`X-mi` o exige. É informação experimental: um braço que precisa executar código
do repositório do modelo não está em pé de igualdade com um que não precisa, e o
texto tem de dizê-lo.

---

## 2026-08-25 — Propagação do fix do `xs:ID` para o texto, e o que ela revelou

Com o `--retranspile` já aplicado, restava propagar os números para a monografia.
O trabalho foi maior do que "trocar 54,7 por 56,6", e o excedente é o achado.

### O que de fato mudou

Só o braço A2g. Nenhuma ordenação de tabela se altera, nenhuma conclusão se
inverte, nenhum desfecho de hipótese muda. Mas o número aparecia em **sete**
lugares, três deles derivados:

| Onde | Antes | Depois |
|---|---|---|
| `tab:res-bracos`, XSD | 54,7% | **56,6%** |
| `tab:res-bracos`, DF-F1 | 0,0773 | **0,0783** |
| `tab:res-testes`, $r_{rb}$ | $-0{,}463$ | $-0{,}429$ |
| `tab:res-testes`, $p_{Holm}$ | 0,0050 | **0,0062** |
| `tab:res-condicional`, todos | $-0{,}0778$ | $-0{,}0768$ |
| `tab:res-condicional`, condicional | 0,0999 / $-0{,}0421$ | 0,1012 / $-0{,}0408$ |
| `tab:res-teto` | 0,0602 / 42% | 0,0624 / 43% |

Mais introdução, conclusão e o quadro-resumo de hipóteses ($p_{Holm}$ 0,005 →
0,006). A `tab:res-mf` foi recomputada e **não mudou** — os dois itens com
`messageFlow` na referência primária não estavam entre as gerações afetadas.

O contraste confirmatório saiu do `run_analysis`, não da minha mão. Ele continua
significativo e H1g continua refutada; o efeito ficou marginalmente menor.

### O achado: a nota da figura estava certa e o código é que estava errado

A `\Nota` da figura de validade afirma que, nos braços de DSL, "a validade XSD
coincide com a taxa de *parsing*, pois a transpilação é determinística e sempre
produz XML válido a partir de DSL aceita".

Antes do fix isso era **falso**: A2g tinha parse 56,6% e XSD 54,7%. Três gerações
faziam *parse* e produziam XML inválido — que é exatamente o que a nota diz não
poder acontecer. A nota não era um erro de redação: era a especificação correta
do transpilador, e a divergência entre ela e os dados era a assinatura do bug do
`xs:ID`, visível na tabela desde antes de eu procurá-lo.

Depois do fix a igualdade vale em **todos** os braços de DSL, exploratórios
inclusive: A2 64,8/64,8, A2g 56,6/56,6, A3 58,5/58,5, A3m 0/0, A4 86,8/86,8,
X-lc25 88,7/88,7, X-lc50 86,8/86,8, X-ds 75,5/75,5.

Fica a lição de auditoria: **uma nota de figura que afirma um invariante é um
teste escrito em português.** Quando os números da própria tabela a contradizem,
a hipótese barata é erro de redação e a hipótese certa era o bug.

### `src/evaluation/run_tabelas.py` — três tabelas que eram digitadas à mão

Ao propagar os números descobri que `tab:res-condicional`, `tab:res-mf` e
`tab:res-teto` não saíam de script nenhum. Reconstruí os três métodos por
tentativa e validei cada um contra os braços que **não** mudaram — critério de
aceitação: reproduzir o valor publicado. Os três reproduzem exatamente, inclusive
a convenção de subtrair valores já arredondados que produz $-0{,}0219$ em vez de
$-0{,}0218$ (o leitor precisa conseguir refazer a conta com o que está impresso).

Definições fixadas no módulo, que eram justamente o que se perdia:

- **condicional**: média das medianas por item, restrita aos itens com ao menos
  uma geração XSD-válida no braço de DSL;
- **MF-F1**: itens cuja referência **primária** contém `messageFlow` — hoje dois
  (`pmo_23`, `pmo_38`). Note que 17 itens têm `messageFlow` em *alguma*
  referência; usar esse recorte daria outra tabela;
- **teto**: itens com referência múltipla (24), porque o teto humano foi medido
  nesses mesmos itens.

A linha "Pipeline de augmentation" da `tab:res-teto` continua fora do script —
não é braço do benchmark, vem do corpus.

Comando: `uv run python -m src.evaluation.run_tabelas`.

### Pendência honesta

Os valores acima estão no texto, mas **o PDF ainda não foi recompilado** nesta
sessão. Antes de considerar o capítulo fechado é preciso compilar e conferir as
três figuras que passaram a ler CSV.

### Achados exploratórios escritos no texto

Nova `\subsection{Braços Exploratórios}` em `resultados.tex`, antes da Síntese,
com abertura declarando que nada ali é confirmatório. Dois achados.

**Curva de aprendizado — uma dissociação.** Treino com 51, 96 e 207 documentos
(167, 339 e 672 exemplos), validação idêntica nos três, frações aninhadas
verificadas por asserção:

| | docs | ex. | *loss* val. | XSD-Val | DF-F1 |
|---|---|---|---|---|---|
| X-lc25 | 51 | 167 | 0,4945 | 88,7% | 0,1000 |
| X-lc50 | 96 | 339 | 0,4488 | 86,8% | 0,1141 |
| A4 | 207 | 672 | **0,4160** | 86,8% | 0,1114 |

A *loss* de validação melhora **monotonicamente** com o volume; as métricas da
tarefa **não acompanham**. Essa é a formulação certa, e é mais forte do que
"a curva saturou": o dado adicional compra verossimilhança e não capacidade. A
diferença de validade entre o menor e o maior ponto são 3 gerações em 159.

Sinal de convergência coerente: os dois pontos reduzidos ainda melhoravam na 3ª
época; o completo teve seu melhor na 2ª e piorou na 3ª. Menos dados, convergência
mais tardia — os pontos reduzidos não foram prejudicados por treino insuficiente.

Implicação que **não** deve ser generalizada: mais seções do mesmo handbook não
compensam. Fontes distintas continuam não testadas.

**Resíduo referencial — corrigi minha própria afirmação.** Eu havia anotado que
"100% das falhas dos braços ajustados são referenciais". **Falso.** Ao recontar
antes de publicar:

| braço | itens que falham / emitem ref | taxa | decomposição |
|---|---|---|---|
| A4 | 7/45 | 15,6% | 5 referência, 2 `UnexpectedEOF` |
| X-lc25 | 6/38 | 15,8% | 3 referência, 2 léxico, 1 EOF |
| X-lc50 | 7/49 | 14,3% | 7 referência |

O correto é **15 de 20 itens** (75%), não 100%. O `UnexpectedEOF` é chave não
fechada, não referência. Também: o "7/7/7" que eu tinha anotado era pré-retranspile
— hoje é 7/6/7, porque o fix do `xs:ID` recuperou um item do X-lc25.

O que **sobrevive** à recontagem, e é o achado de fato:

1. **O ajuste fino elimina a falha léxica.** A3 (mesmo modelo base, gramática no
   *prompt*) falha 66/66 por caractere inesperado e **zero** por referência. Os
   braços ajustados invertem isso. Aprender a notação é deixar de errar a
   superfície.
2. **A taxa condicional é estável em 14,3–15,8%** apesar de volumes de treino
   muito diferentes — propriedade da notação, não do volume.
3. Nos braços ajustados as falhas são **determinísticas por item**: as 3
   repetições falham em conjunto (21 = 7×3, 18 = 6×3).

A propriedade "falhas ⊂ itens que emitem ref" é verdadeira nos três, mas **não
prova nada sozinha**: com 45 dos 53 itens emitindo referência, 7 falhas
aleatórias cairiam todas dentro em ~28% das vezes. O sinal está no *tipo* do
erro (`Unresolved DSL ref`), não na inclusão.

**Implicação de projeto (verificada no código, não suposta).**
`xml.py:114-126` resolve na ordem: identificador explícito → *slug* do rótulo →
declaração adiante. Referenciar pelo rótulo já emitido **já funciona hoje**. O
modelo falha por inventar `#t07` opaco que nunca declarou — ou seja, por ter de
manter estado arbitrário ao longo da geração. Trocar a convenção removeria a
classe dominante de falha, ao custo de mais *tokens*: tensão direta com o eixo
econômico. Fica como trabalho futuro, não testado.

### E-2 no texto, e um módulo a menos de números digitados

A subseção de emendas virou plural, com E-1 (glosa do *prompt*, penalizava o
autor) e E-2 (fix do `xs:ID`, **favorece** o autor). A assimetria é o ponto e
está escrita como tal: três salvaguardas declaradas (correção aplicada a todos os
braços ao mesmo tempo, por reprocessamento determinístico da saída bruta, sem
nova chamada a modelo), efeito reportado por inteiro (6 linhas em 1.590), e o
registro de que **o A4 não mudou** — o resultado central não foi tocado pela
correção que o beneficiaria.

Verificações: PDF recompilado três vezes sem erro; nenhum valor antigo sobrevive
no PDF (`54,7`, `0,0773`, `0,0602`, `0,0778`, `0,463` → zero ocorrências); figura
de validade inspecionada visualmente. 295 testes passando, ruff limpo.

Nota sobre a figura de custo: A2g e A3 passaram a quase se sobrepor (56,6% vs
58,5% de validade, 149 vs 159 *tokens*). Os rótulos não colidem e a proximidade é
o que os dados dizem — não é defeito de figura.

---

## 2026-08-25 (noite) — Diagnóstico da falha referencial: é a notação, não o modelo

O vigia da avaliação do X-gr despejou as falhas no log e elas eram todas do
mesmo tipo. Isso puxou uma investigação que fechou o mecanismo.

### O que a saída mostra

Exemplo real (X-gr, `pmo_14`), reduzido ao essencial:

```
@lane "Department" {
  -> user "Review Plan in Strategic Alignment Meeting"    <- alvo, sem #id
  ...
  -> xor "Adjustments Needed?" {
  [adjustments needed] -> user "Document Adjustments" -> ... -> #t03   <- falha
```

É uma **aresta de retorno**. O modelo sabe para onde quer voltar; o que ele não
fez foi marcar o alvo lá atrás, quando o emitiu.

### A causa: a notação exige antecipação que um gerador esquerda-direita não tem

Medições no `train.jsonl` (690 exemplos):

- **690/690 declaram todas as referências que usam.** Zero contraexemplos. O
  modelo não está copiando dado ruim.
- Mas **151 das 200 referências apontam para trás**, mediana de 334 caracteres
  de distância (máx. 1793).
- A convenção `#tNN` domina o treino: **753 ocorrências** contra 398 de outras
  formas.
- Só **121 dos 690** exemplos (17,5%) contêm alguma referência.

O treino é perfeito porque saiu de transpilação determinística, que conhece o
grafo inteiro antes de escrevê-lo. O gerador autorregressivo, não. Para acertar
uma referência para trás ele teria de saber, ao emitir um nó, que um ramo ainda
não escrito voltaria a ele. **Isso não é aprendível com mais dados** — e explica
por que a taxa de falha é estável em 14–16% entre volumes de treino muito
diferentes, e por que replica entre famílias.

### O modelo é sistemático, não alucinado

`#tNN` é usado **posicionalmente**: `#t03` = terceira tarefa emitida. Aplicando
essa regra e trocando pelo *slug* do rótulo correspondente:

| braço | reparo posicional válido |
|---|---|
| A4 (Qwen) | 12/15 |
| X-gr (Granite) | **24/24** |

Para o X-gr a regra posicional é **cega e determinística** — sem oráculo — e
recupera tudo. Para o A4 precisa de busca em 3 dos 15 casos.

E, buscando entre todos os rótulos, **100% das falhas referenciais dos dois
braços viram XSD-válidas** (15/15 e 24/24) trocando *só a forma da referência*.
O corpo do documento está correto; falha apenas o endereçamento.

### Onde a evidência para — o limite que tenho de escrever

Testei se o reparo posicional é *semanticamente* melhor que um arbitrário:

| braço | posicional | arbitrário | braço nas que já validam |
|---|---|---|---|
| A4 | 0,0989 | 0,0791 | 0,1283 |
| X-gr | 0,1251 | 0,1247 | 0,1195 |

No A4 o posicional é melhor; no X-gr é **indistinguível**. A razão é de poder
estatístico: uma aresta de retorno é uma entre dezenas do multiconjunto, e
realocá-la quase não move o DF-F1. **A evidência sustenta que o esquema é
sistemático; não sustenta que seja correto.** Escrito assim no texto.

O teto de 96,2% (A4) e 98,1% (X-gr) é **limite superior**, não desempenho.

### O custo da solução foi medido, e derruba a objeção que eu mesmo levantei

Eu havia escrito no artigo que referenciar por rótulo teria "custo em *tokens*
maior, o que a coloca em tensão direta com o eixo econômico". **Errado.**
Reescrevendo o corpus com `#slug` no lugar de `#tNN`, com o tokenizador do Qwen:

```
519 exemplos com referência
tokens: 173.569 -> 177.573  (+2,31%)
custo médio: +7,7 tokens por exemplo
```

TCR iria de ~7,0 para ~6,8. Contra 85% de economia, é gratuito. Corrigi o texto.

`resolve_ref` (`xml.py:114-126`) **já** resolve por *slug* — a mudança é de
convenção do gerador de dados, não do transpilador. Continua não testada:
exigiria retreinar sobre o corpus reescrito. É o trabalho futuro mais bem
fundamentado que esta avaliação produziu.

### Por que isso não aparece nos braços não ajustados

A3 (mesmo modelo base, gramática no *prompt*) falha 66/66 por caractere
inesperado e **zero** por referência — ele emite referência em apenas 5 dos 53
itens. A convenção `#tNN` é **aprendida no ajuste fino**. O ajuste ensina a
superfície da notação e, junto, uma dívida que a notação cobra depois.

### Predição do mecanismo: ciclo na referência (corroborada, não estabelecida)

Se a falha vem de aresta de retorno, ela deve concentrar-se nos itens cuja
referência tem **ciclo**. Direção confirmada:

| braço | falhas referenciais em itens com ciclo | falhas em itens acíclicos |
|---|---|---|
| A4 | 5/5 | 0 de 13 itens |
| X-gr | 8/8 | 0 de 13 itens |

Mas **40 dos 53 itens têm ciclo**, então o denominador explica muito. Fisher
exato unilateral: A4 p = 0,23; X-gr p = 0,09. **Nenhum atinge significância.**
Agregar os dois dá p = 0,014 e **não é lícito** — os braços compartilham os
mesmos 53 itens, não são amostras independentes (3 itens falham em ambos).

Vale como corroboração do mecanismo — a predição foi feita **antes** da medição
e nenhum item acíclico jamais falhou — e não como estabelecimento da associação.
Escrito no texto com essa ressalva explícita.

---

## 2026-08-25 23:32 — Cadeia de replicação completa

| braço | modelo base | tokenizador | XSD | itens | DF-F1 |
|---|---|---|---|---|---|
| A4 | Qwen2.5-Coder-7B | 151.665 `Qwen2Tokenizer` | **86,8%** | 46/53 | 0,1114 |
| X-gr | Granite 4.1-8B | 100.352 `GPT2Tokenizer` | 83,0% | 44/53 | 0,0992 |
| X-mi | MiMo-7B-RL | 151.665 `Qwen2Tokenizer` | 83,0% | 44/53 | 0,1009 |

**O método replica.** Granite e MiMo caem no mesmo ponto exato — 132/159, 44/53.
Diferença para o Qwen: 3,8 pontos, seis gerações. Nenhuma réplica supera o
original, nenhuma fracassa. Compromisso pré-registrado cumprido: as duas
treinadas entraram no texto.

### O controle do tokenizador — não estava planejado e é o achado da noite

Verifiquei antes de afirmar: **MiMo usa o tokenizador exato do Qwen** (mesma
classe, mesmas 151.665 entradas); Granite usa outro, com 2/3 do vocabulário.

| braço | itens em que usa `#ref` | falhas ref | taxa |
|---|---|---|---|
| A4 (Qwen) | 45 | 5 | **11,1%** |
| X-gr (Granite) | 23 | 8 | 34,8% |
| X-mi (MiMo) | 24 | 8 | 33,3% |

**MiMo comporta-se como Granite, não como Qwen.** Logo a divergência no uso de
referências **não é artefato de tokenização** — é do pré-treinamento. Só foi
possível afirmar porque os dois braços rodaram; com um só, seria confundível.

Duas estratégias diante da mesma dificuldade: Qwen usa a construção à vontade e
erra pouco; os outros dois a evitam (metade dos itens) e erram 3× mais quando
arriscam.

### O diagnóstico replica em três famílias

Reparo posicional (regra cega, sem oráculo): **24/24 no X-gr, 24/24 no X-mi**,
12/15 no A4. Teto de validade 96,2% / 98,1% / 98,1%. Predição do ciclo: 5/5,
8/8, 8/8 — e zero falhas nos 13 itens acíclicos em qualquer braço (Fisher
p = 0,23 / 0,09 / 0,09; segue subdimensionado, escrito como corroboração).

Em três famílias independentes, **toda** falha referencial é reparável trocando
só a forma da referência. O gargalo é a exigência de antecipação da notação.

### Escrito no texto

Nova `\subsubsection*{Replicação em outras famílias de modelos}` com as duas
tabelas, o controle do tokenizador, e — explicitamente — o **X-ds invalidado**
(tokenizador que quebra ida-e-volta; 75,5% que não medem o método) e o **X-ms
não executado** (portão do MiMo passou). A distinção entre "não replicou" e
"não foi medido" está no texto, que é o que a omissão destruiria.

Correções feitas ao incorporar as réplicas:
- `\verb|#ref|` em cabeçalho de tabela → erro fatal (`#` é caractere de
  parâmetro em modo horizontal restrito). Trocado por `\texttt{\#ref}`.
- X-mi falha em **9** itens (8 referenciais + 1 léxico), não 8 — corrigido na
  tabela do resíduo.
- A prosa do resíduo falava em "três braços / 20 falhas / 15 referenciais";
  com cinco braços é **38 falhas, 31 referenciais (82%)**. Reescrita.
- A afirmação "taxa condicional estável" passou a distinguir dois regimes:
  estável em 14–16% **dentro da família Qwen** (volumes variando 4×), e 37–39%
  nas outras duas — sobre base menor de itens. O que não varia é a natureza.

Estado: 295 testes, ruff limpo, PDF 103 páginas compilando sem erro.

---

## 2026-08-30 — A Conclusão contrariava os Resultados; ao corrigir, um número da tab:res-oraculo veio junto

Gatilho: conferir se o artigo acompanhava as réplicas Granite/MiMo. A resposta
é que **os Resultados acompanhavam; a Conclusão, não** — escrita em 17/08, antes
das réplicas de 25/08, dizia que a replicação do ajuste fino "não foi realizada"
e a listava como trabalho futuro, contradizendo a `tab:res-replicacao` do próprio
documento. Ao corrigir isso, a passagem citava o oráculo como **0,1533**, valor
que **não existia em tabela alguma** do artigo — e a investigação desse descompasso
revelou o problema real, que está na tabela, não na Conclusão.

### O número do oráculo: duas regras de pontuação numa tabela só

A `tab:res-oraculo` dizia **0,1236**. Reproduzindo com `score_candidate` (a
função do benchmark, regra congelada da spec 003 §4: máximo sobre referências
admitidas):

| medição | regra | valor |
|---|---|---|
| oráculo, 53 itens | máximo (regra dos braços) | **0,1533** |
| oráculo, 53 itens | só referência primária | 0,1236 |
| oráculo, 24 itens c/ ref múltipla | máximo | 0,1103 (= 76% do teto ✓) |

A linha do pipeline na tabela foi gerada por sonda **primária-only**; as demais
linhas (A1 0,1942, A2 0,1375) vêm da regra do máximo. Três evidências
independentes confirmam que o 0,1533 é o número da regra congelada:

1. **A prosa da própria seção só é verdadeira com 0,1533**: "acima de todos os
   braços que emitem DSL" — com 0,1236 o oráculo ficaria **abaixo** do A2
   (0,1375). A frase foi escrita para o valor máximo e publicada ao lado do
   valor primário-only.
2. O registro de 2026-08-16 declara "com a regra do máximo, dá 0,1533".
3. A `tab:res-teto` (24 itens, via `run_tabelas.py`) já usava o máximo e bate:
   0,1103 reproduzido hoje.

**Corrigido**: célula do DF-F1 na `tab:res-oraculo` (0,1236 → 0,1533, linha
reordenada entre A1 e A2 para manter ordem decrescente) e a frase "situa-se em
0,1236" na prosa. A Conclusão já dizia 0,1533 — **não foi tocada nesse número**.

**Direção do viés da correção**: o teto do oráculo **sobe**, o que **enfraquece**
a desculpa do teto para o DF-F1 do A4 (0,1114) — o headroom passa de ~0,012
para ~0,042. Correção desfavorável ao autor, que é a direção segura; registrada
aqui por pertencer à mesma classe de rigor que as emendas E-1/E-2.

**Coluna "Rótulos alinhados" — NÃO corrigida, e por quê.** A célula do pipeline
(32,3%) reproduz exatamente como estatística primária-only (37,5% sob a regra do
máximo). As células de A1 (40,5%) e A2 (48,6%) **não reproduziram** sob nenhuma
convenção testada (máximo+zero-fill dá 44,4%/31,3%; só-válidas+máximo dá
~45%/~48,3%). Sem recuperar a convenção das sondas originais, mudar a célula do
pipeline para 37,5% criaria inconsistência nova na coluna. Ação remanescente:
recalcular a coluna inteira sob a regra congelada (ou removê-la) quando houver
tempo de auditoria; os valores de DF-F1 da tabela estão, todos, sob a regra
congelada.

### Conclusão — quatro passagens reescritas

| passagem | antes (17/08) | depois |
|---|---|---|
| Limitações | "Um único modelo base... não foi realizada no eixo do ajuste fino" | "Replicação do ajuste fino apenas exploratória": feita (Granite/MiMo 83,0% vs 86,8%), mas sem força confirmatória; quarta família invalidada por tokenização; divergência de comportamento referencial (14–16% vs 37–39%) é do pré-treino |
| Contribuições | sem menção à replicação do SFT | acrescentada uma oração na "Viabilidade econômica" |
| Futuro: "Replicação com segundo modelo base" | descrita como pendente | **substituída** por "Convenção de referência por rótulo na notação" (151/200 refs para trás; custo medido 2,31%; o futuro mais bem fundamentado que a avaliação produziu) |
| Futuro: "Curva de aprendizado" | descrita como pendente | **substituída** por "Ampliação do corpus por fontes distintas" (a curva rodou; o que resta é fonte nova) |

Resumo e Abstract ganharam uma oração: o patamar de validade "replicou-se, em
verificação exploratória, em duas famílias adicionais de modelos". Nota de
trabalho no topo de `resultados.tex` ("Falta só o A4") atualizada.

### Verificação

- Recompilado com a sequência completa (pdflatex/bibtex/makeglossaries/2×pdflatex):
  **103 páginas, zero erros, zero referências indefinidas**.
- PDF conferido: "0,1236" não ocorre; "0,1533" ocorre 3× (tabela, prosa,
  Conclusão); nenhuma passagem antiga sobrevive.
- Reprodução do oráculo documentada acima via `score_candidate` — a sonda
  primária-only também reproduz (0,1236), o que confirma a causa-raiz.

### Lição, da mesma família das anteriores

A `tab:res-oraculo` foi a única tabela de números derivados que **não** entrou
no `run_tabelas.py` na sessão de 25/08 ("não é braço do benchmark, vem do
corpus") — e foi justamente a que manteve valor de sonda com regra distinta da
das demais linhas. **Tabela com números de origens distintas é tabela com duas
regras**: se a linha não vem de script, ela precisa de um comando de reprodução
documentado, ou o valor congela sem que ninguém saiba sob qual convenção.

---

## 2026-08-30 (noite) — As hipóteses estavam só no capítulo que as testa

Auditoria de consistência artigo × projeto. Achado principal: **H1, H1g, H2, H3
e H4 apareciam exclusivamente em `resultados.tex`** (30 ocorrências) — enunciadas
pela primeira vez, para o leitor, dentro da tabela que já traz o desfecho de cada
uma. A Metodologia nunca as declarava, embora a Introdução prometesse que o
capítulo reproduz o protocolo "na íntegra, incluindo hipóteses" e a §pré-registro
afirmasse que "hipóteses foram registradas com direção esperada".

O pré-registro existia e estava correto (`specs/003-eval-harness/spec.md` §6.1);
o que faltava era a transcrição para a monografia. Isso importa mais do que
parece: o valor argumentativo do pré-registro depende de o leitor ver o enunciado
**antes** do resultado, e quem lê só o PDF via o inverso.

### O que foi escrito

Nova `\subsection{Hipóteses}` (§4.7.7, `subsec:hipoteses`), entre o desenho dos
braços e os parâmetros congelados, com `tab:hipoteses` (Tabela 3) e um parágrafo
por hipótese. O texto é **transcrição** do spec §6.1, não redação nova — nenhum
enunciado foi reformulado, e por isso a mudança **não é emenda** ao protocolo:
é a documentação do que já estava congelado. A tabela distingue explicitamente
as três hipóteses que entram no teste com correção de Holm (H1, H1g, H3) das
duas reportadas descritivamente (H2, H4), distinção que o capítulo de resultados
aplicava sem nunca ter enunciado.

Três pontos que só existiam no spec e agora estão no texto:

- **H2 supõe a etapa anterior.** O enunciado atribui a validade ao transpilador
  e toma como cumprida a aceitação da DSL pela gramática. Escrito de forma
  descritiva, sem antecipar o resultado — é o que torna legível, no capítulo 5,
  a frase "o protocolo tratava o parsing como etapa dada, e é ele o gargalo".
- **Regra de leitura de H3**, fixada antes dos dados: sendo `≥`, um empate
  estatístico não a refuta nem a demonstra; quem responde não inferioridade é o
  IC, não a ausência de significância.
- **O limiar de H4 é piso, não expectativa** — a medição do corpus já dava ~6
  quando o 2 foi fixado.

### Defasagem menor corrigida junto

A **lateralidade bilateral** estava em `resultados.tex` ("teste de Wilcoxon
pareado bilateral") e no spec §6.3, mas **não** na Metodologia, que descrevia o
teste sem dizer se era uni ou bilateral. Acrescentada com a justificativa
registrada (hipóteses direcionais, alegação de não inferioridade respondida pelo
IC, bilateral como escolha conservadora), mais o descarte de diferenças nulas
(`zero_method="wilcox"`, conferido em `run_analysis.py:93`) e a nomeação
explícita dos três contrastes. Referência cruzada acrescentada em §5.6.2.

### Verificação

- Sequência completa (pdflatex/bibtex/makeglossaries/2×pdflatex): **104 páginas,
  zero erro, zero citação ou referência indefinida** (era 103).
- PDF conferido: Tabela 3 renderiza; as remissões resolvem para 4.7.6, 4.7.8,
  5.4 e 5.6.2; nenhuma tabela posterior perdeu numeração.
- Os números da monografia foram reconferidos contra o banco nesta mesma
  auditoria (`run_analysis` e `run_tabelas` reproduzem `tab:res-testes`,
  `tab:res-condicional`, `tab:res-mf` e `tab:res-teto` dígito a dígito; eixo 2 e
  composição do corpus idem). Nada além do texto acima mudou.

### Pendências da mesma auditoria, ainda abertas

1. `tab:bracos` lista **6 braços e não inclui o A3m**, enquanto §5.6 fala em
   "7 braços × 53 × 3 = 1.113 gerações" e o spec §7 já traz o A3m.
2. Coluna "Rótulos alinhados" da `tab:res-oraculo` — pendência herdada da sessão
   anterior, com duas convenções na mesma coluna.
3. `tab:res-teto` não tem linha do **A4** (medido nesta auditoria: **0,0782 nos
   24 itens, 54% do teto**); `run_tabelas.py` também não o calcula. Incluir a
   linha não move afirmação alguma — o pipeline (0,1103) segue acima.
4. `fig:df-f1-teto` compara barras de 53 itens com linha de teto de 24 itens.
5. Pós-textuais ainda são do template-exemplo (glossário de "Braile/Borboleta",
   apêndices com *lorem ipsum* e "Termo de Fiel Depositário", anexos, errata de
   tese de veterinária, agradecimentos/dedicatória/epígrafe de outra pessoa) —
   ~10 páginas do PDF. Não estavam registradas em lugar nenhum.

---

## 2026-08-30 (noite, cont.) — O A3m entra na tabela de braços, e traz junto a dimensão do *prompt*

Pendência 1 da auditoria anterior. A `tab:bracos` listava **6 braços**, enquanto
a §5.6 abre com "1.113 gerações (7 braços × 53 × 3)" e o `run_benchmark.py` e o
spec §7 já traziam o **A3m**. O leitor encontrava, no capítulo de resultados, um
braço com "função de piso que lhe foi atribuída no desenho" — atribuição que o
desenho não registrava.

### Por que não era acrescentar uma linha

A3m difere do A3 **apenas pelo \textit{prompt}**, e a Metodologia não descrevia
os \textit{prompts} do benchmark em lugar nenhum — nem os três regimes, nem a
garantia de equidade entre eles. Acrescentar a linha sem isso produziria duas
linhas idênticas (mesmo modelo, mesma saída) com papéis diferentes e nenhuma
explicação da diferença.

A tabela ganhou, então, uma coluna **\textit{Prompt}** (notação XML · gramática ·
mínimo), e o capítulo ganhou três parágrafos:

1. **Os três regimes de instrução**, com o registro de que o \textit{prompt}
   mínimo é *deliberadamente* o mesmo do treino do SFT — para que a inferência
   do A4 ocorra na distribuição em que ele foi treinado. Custo de entrada: 756
   \textit{tokens} contra 1.354 do que carrega a gramática (números que já
   estavam na §4.8.1 e na §5.6.4; nenhum valor novo foi introduzido).
2. **A equidade entre formatos**, que estava travada por
   `tests/evaluation/test_benchmark_prompts.py` desde 15/08 e **nunca havia sido
   afirmada na monografia**: blocos `role`, `language`, `modeling_rules` e
   `output_contract` idênticos byte a byte nos três, e os exemplos de notação do
   XML e da DSL provados como **o mesmo processo** (transpila e compara: DF-F1
   = 1,0). É a garantia de que o contraste A2 vs A1 mede o formato e não a
   redação — sem ela, H1 não se sustenta como enunciada.
3. **A função do A3m**: sem ele, A4 vs A3 varia pesos *e* instrução ao mesmo
   tempo. A4 vs A3m isola o adaptador; A4 vs A3 mede a intervenção inteira.
   Ambos exploratórios, fora da correção de múltiplas comparações.

### Defasagem menor corrigida junto

"Os **dois** braços executados com o modelo pequeno (A3 e A4) usam configuração
de inferência idêntica" → **três** (A3, A3m e A4). Conferido em `ARMS`: os três
são `backend="local"`, mesmo modelo, mesmo teto de 2.048.

### Verificação

- **105 páginas** (era 104), zero erro, zero referência indefinida.
- Tabela renderiza com as 7 linhas dentro da largura do texto; o único
  \textit{overfull} relevante do documento (43,2\,pt) é **pré-existente** e está
  na capa (`main.tex:168`, `\imprimircapa`), não na tabela nova.
- Nenhuma outra contagem de braços no texto ficou defasada (`grep` por "seis/
  cinco/quatro/dois braços": as ocorrências restantes são corretas — "cinco
  braços ajustados" são A4 + X-gr + X-mi + X-lc25 + X-lc50).

### Lição, repetida

A tabela do desenho estava atrasada porque o braço foi acrescentado **no código
e no spec**, e a tabela é prosa escrita à mão. Mesma família do problema da
`tab:res-oraculo`: o que não vem de script diverge da fonte sem que ninguém
perceba. Aqui não dá para gerar a tabela por script, mas dá para o teste do
benchmark falhar quando `ARMS` e o texto divergirem — anotado como ideia, não
implementado.

### Pendências que seguem abertas

2. Coluna "Rótulos alinhados" da `tab:res-oraculo` (duas convenções na mesma coluna).
3. `tab:res-teto` sem a linha do A4 (**0,0782 nos 24 itens, 54% do teto**).
4. `fig:df-f1-teto` compara barras de 53 itens com linha de teto de 24.
5. Pós-textuais ainda são do template-exemplo (~10 páginas do PDF).

---

## 2026-08-30 (madrugada) — A coluna de rótulos, recalculada sob a regra congelada, e o que ela derrubou

Pendência 2. A coluna "Rótulos alinhados" da `tab:res-oraculo` tinha duas
convenções na mesma coluna e nenhuma reproduzia. Em vez de arqueologia, a
definição foi **implementada** — `rotulos_alinhados` em `run_tabelas.py`, com
`oraculo()`, `teto_rotulos()` e `ancoragem()` — e a tabela inteira foi refeita
por script. Quatro testes novos (`tests/evaluation/test_tabelas.py`) fixam a
convenção em código: 299 testes no total, ruff limpo.

### Convenção declarada (agora impressa na nota da tabela)

- **Unidade**: item. Mediana das k=3 repetições, depois média (taxas) ou mediana
  (contagens) entre itens — a mesma agregação do DF-F1.
- **Referência**: a que venceu pela regra do máximo, lida de `benchmark_eval.
  ref_variant`; para o pipeline, recalculada com `compare_xml`. Empate resolvido
  pela primeira referência, como em `score_candidate` — **o desempate vale
  0,8 ponto percentual no teto humano** (0,313 contra 0,305), então não podia
  ficar por conta da ordem de iteração.
- **Denominador**: só as gerações **válidas**, com o `n` impresso. Documento
  inválido não tem rótulo a comparar, e zerá-lo faria a coluna medir validade —
  que é o que a coluna de DF-F1 já mede. É a única forma de as três colunas
  conviverem sem virar duas convenções outra vez: cada uma declara a sua.
- **Categorias anônimas fora**: `<start>`/`<end>` são tipo, não denominação.
  Incluí-las dava 44,4% no A1 em vez de 40,1% — inflação pura.

### Números novos

| origem | DF-F1 | rótulos | arestas | n |
|---|---|---|---|---|
| gold | --- | --- | 18 | 53 |
| A1 | 0,1942 | **40,1%** | 12 | 53 |
| pipeline | 0,1533 | **41,3%** | 14 | 53 |
| A2 | 0,1375 | **40,5%** | 13,5 | 40 |
| A4 | 0,1114 | **38,2%** | 13 | 46 |

Teto humano de rótulos: **30,5%** (era 31,0% — praticamente o mesmo, o que dá
alguma confiança na sonda original *desse* número). Linha do **A4 acrescentada**:
o braço proposto faltava na tabela que estima o teto dele.

O efeito na tese é favorável e não foi procurado: o pipeline alinha **41,3%**
contra 30,5% entre especialistas — antes o texto dizia 32,3% vs 31,0% ("dentro
da faixa humana"), agora é **acima** dela, e *todas* as origens ficam em 38–41%.
A conclusão "não há nomenclatura a corrigir" fica mais forte, não mais fraca.

### O que a mesma varredura derrubou — e isto é desfavorável

O parágrafo vizinho citava a **ancoragem no texto-fonte** (62,1% pipeline ·
60,4% A1 · 60,8% gold) para descartar a hipótese de que os dois saltos de LLM
afastariam o vocabulário da fonte, concluindo que "o pipeline é, dos três, o
**mais** ancorado". Implementada a medição (`ancoragem()`), os valores são
**69,6% pipeline · 69,9% gold · 76,1% A1**, e a **ordenação se inverte**: o
pipeline não é o mais ancorado, é *tão* ancorado quanto o especialista humano
(diferença de 0,3 pp), e o modelo de fronteira está acima dos dois.

A hipótese segue descartada — empatar com o humano é o que a pergunta exigia —,
mas o texto perdeu uma vantagem que reivindicava. Reescrito nesses termos.
Direção da correção: **contra o autor**, como a do oráculo em 0,1533.

### Propagação (o PDF não contém mais nenhum dos números antigos, conferido)

- `tab:res-oraculo`: tabela, coluna `n`, linha do A4 e nota nova.
- §5.6.9: ancoragem reescrita; parágrafo da escolha lexical com 41,3% vs 30,5%,
  agora com a ressalva de que o teto humano vem dos 24 itens com referência
  múltipla, e o resto dos 53 — comparáveis em ordem de grandeza, não célula a célula.
- §5.6.8: teto de rótulos 31,0% → 30,5%, e a aritmética $0{,}31^2\\approx0{,}10$
  → $0{,}305^2\\approx0{,}09$.
- §5.6.7: "apenas 53% dos rótulos" → **40,5%** (a sonda antiga também não
  reproduzia aqui), e "12 na referência contra 11 no candidato" → **12 contra 9,5**.
- §4.9.2 (recompensa do GRPO): faixa de ancoragem 60,4–62,1% → **69,6–76,1%**.
- Conclusão: 31,0% → 30,5% dos rótulos.
- Compilação: **106 páginas**, zero erro, zero referência indefinida.

### Lição

Três das quatro sondas avulsas deste capítulo não reproduziram, e uma delas
sustentava uma afirmação **invertida**. O que separou as que sobreviveram das
que caíram não foi cuidado na hora de medir — foi haver, ou não, um comando que
as refizesse. Nenhum número derivado deve entrar no texto sem função no
`run_tabelas.py` (ou equivalente) e teste que fixe a convenção.

### Pendências

3. `tab:res-teto` sem a linha do A4 (**0,0782 nos 24 itens, 54% do teto**).
4. `fig:df-f1-teto` compara barras de 53 itens com linha de teto de 24.
5. Pós-textuais ainda são do template-exemplo (~10 páginas do PDF).

---

## 2026-08-30 (madrugada, cont.) — O teto humano passa a ser comparável, e a figura deixa de mentir por escala

Pendências 3 e 4, que eram o mesmo problema visto de dois ângulos: a
`tab:res-teto` restringia tudo aos 24 itens com referência múltipla, mas a
`fig:df-f1-teto` desenhava **barras de 53 itens sob uma linha de teto de 24** —
e a `fig:limiar` fazia o mesmo com suas quatro séries.

### O que a escala misturada escondia

Na figura antiga o A2 aparecia a 0,1375, encostado no teto de 0,1449, sugerindo
que os braços de DSL chegavam perto da concordância humana. No recorte
comparável o A2 vale **0,0498** — um terço do teto. A figura e a tabela do mesmo
capítulo diziam coisas diferentes sobre o mesmo braço, e a nota da figura
("apenas os dois braços de XML direto o ultrapassam") era falsa nesse recorte:
**só o A1 ultrapassa**; o A1g fica em 89%, como a tabela já dizia.

### Feito

- `export_figuras`: `df_f1*.csv` e `limiar.csv` passam a ser calculados **só
  sobre os 24 itens**, com o critério de admissão unificado com o da tabela
  (nota ≥ 4, ≥ 2 referências — dá os mesmos 24 que a regra anterior, mas por
  definição e não por acidente dos dados).
- `run_tabelas.teto`: agora emite **todos os sete braços mais o pipeline**, em
  ordem decrescente, e **calcula o teto** em vez de lê-lo de uma constante —
  era o último número derivado do capítulo que vivia como literal no código.
  Confirmou o valor publicado: **0,1449** exato.
- `tab:res-teto`: acrescentadas as linhas do **A4 (0,0782, 54%)** e do A3m
  (0,0000), e o teto passou de cabeçalho a **linha em posição ordenada** —
  com um braço acima dele, cabeçalho induzia a ler o teto como máximo.
- `fig:df-f1-teto` e `fig:limiar`: barras/séries no recorte de 24, ordem
  refeita, escalas ajustadas (`ymax` 0,225 → 0,205 e 0,42 → 0,36) e notas
  declarando o recorte.
- Prosa: "nenhuma série ultrapassa 0,38" → **0,33** (máximo real do A1 a 0,01);
  o teto agora é descrito como ficando entre o A1 e os braços de DSL em toda a
  faixa; Conclusão corrigida de "os dois braços de geração direta a ultrapassam"
  para **apenas um**.

### O achado que a correção produziu, e como foi escrito

No recorte comparável o **A4 (0,0782) fica acima do A2 (0,0498) e do A2g
(0,0624)** — ordem invertida em relação aos 53 itens, onde o A2 lidera. É
tentador vender isso como vitória do modelo especializado. Está escrito como o
contrário: com n = 24 e diferenças dessa magnitude, a inversão é **evidência de
fragilidade da ordenação**, e reforça a cautela que a Conclusão já registrava.

### Refatoração de passagem

`run_tabelas.py` chegou a 341 linhas. A definição da métrica (`label_alignment`,
`activity_labels`) foi para `topology.py`, onde `align_labels` já mora: métrica
é responsabilidade de topology, montagem de tabela é de run_tabelas. O módulo
voltou a 313 linhas e o teste passou a importar do lugar certo. Números
reconferidos após o movimento: idênticos.

### Verificação

- 299 testes, ruff limpo, `run_tabelas` reproduz tudo.
- **106 páginas**, zero erro, zero referência indefinida.
- Figura conferida em imagem, não só em log: barras na ordem nova, linha do teto
  cruzando apenas o A1, rótulos sem colisão.

### Pendência que sobra

5. Pós-textuais ainda são do template-exemplo: glossário de "Braile/Borboleta",
   apêndices com *lorem ipsum* e "Termo de Fiel Depositário", anexos de outro
   TCC, errata de tese de veterinária, agradecimentos/dedicatória/epígrafe
   escritos na voz de outra pessoa. ~10 páginas do PDF.

---

## 2026-08-30 (madrugada, cont.) — Saem 16 páginas de TCC alheio

Pendência 5, a última da auditoria. O PDF de 106 páginas carregava, do template
de exemplo, um glossário de "Braile/Borboleta", três apêndices (*lorem ipsum*,
"Modelo de Capa" e um Termo de Fiel Depositário de uma Secretaria Municipal de
Saúde), dois anexos de outra área, uma errata de tese de veterinária, e
dedicatória, agradecimentos e epígrafe escritos na voz de outra pessoa
("nestes anos como universitária", com um `\textcolor{red}{Recuo de parágrafo.}`
literal). Nada disso estava registrado como pendência em lugar nenhum.

### Base normativa da remoção

NBR 14724: errata, dedicatória, agradecimentos, epígrafe, listas de ilustrações
e afins, glossário, apêndices, anexos e índice são **opcionais**. Obrigatórios
são folha de rosto, folha de aprovação, resumo, abstract, sumário, texto e
referências — todos preservados. Decisão do Rafael quanto a dedicatória e
agradecimentos: remover, por não serem relevantes ao trabalho.

### Feito

- `main.tex`: removidas as chamadas de errata, dedicatória, agradecimentos,
  epígrafe, glossário, apêndices, anexos e índice — cada bloco substituído por
  um comentário dizendo o que saiu, por que é opcional e como reativar.
- Removidas também as **listas de quadros e de algoritmos**, que imprimiam
  título com página em branco: o trabalho não usa nenhum dos dois. A de
  códigos-fonte fica (tem o exemplo da DSL).
- Índice: sairia vazio de qualquer forma. O único `\index{AAA}` do documento
  estava dentro de um anexo do template.
- Nove arquivos de exemplo apagados (`git rm`, histórico preservado).
- `elementos-pos-textuais/glossario.tex` **esvaziado, não apagado**:
  `lib/unifortex2.sty:33` o carrega no preâmbulo, então apagá-lo exigiria mexer
  no `.sty` do template. Esvaziar desliga o glossário sem tocar no template.

### Verificação

Recompilado do zero (aux/toc/bbl/glo apagados antes, para que sumário e listas
não herdassem entradas mortas): **90 páginas**, zero erro, zero referência
indefinida. Varredura no texto do PDF por "braile/borboleta/lorem ipsum/fiel
depositário/classes sociais/errata/glossário/apêndice/anexo/índice": a única
ocorrência restante é a palavra "apêndice" na Metodologia, descrevendo o
apêndice de nós não emitidos do linearizador. Documento termina em REFERÊNCIAS.

### Dois placeholders que sobram, e que não são meus para preencher

1. **Ficha catalográfica** (obrigatória): `ficha-catalografica.pdf` ainda é a
   folha de instruções do template ("gere no site da biblioteca da Unifor").
   Precisa ser gerada no formulário da Biblioteca Central e substituída.
2. **Folha de aprovação**: imprime "Membro da Banca Dois/Três/Quatro". Ou se
   preenchem os nomes em `main.tex`, ou, depois da defesa, troca-se pela
   digitalização assinada — o fluxo já está documentado em comentário no
   próprio `main.tex`.

---

## 2026-08-30 (madrugada, cont.) — O resumo era o único lugar do documento que exagerava

Auditoria do `abstract.tex` (e do `resumo.tex`, que anda junto). Conformidade e
números estavam certos: parágrafo único, ~330 palavras (NBR 6028 pede 150–500),
tradução fiel sentença a sentença, e todos os valores conferidos contra o banco.

O problema era **de omissão**. O resumo dizia que o modelo especializado atingiu
86,8%, superou o modelo de fronteira instruído por *prompt*, emite um terço dos
*tokens* e custou menos de um dólar — e parava aí. Quem lesse só o resumo
fecharia achando que a proposta venceu. A Conclusão diz o contrário em duas
frentes: 86,8% segue **abaixo dos 98,1%** da geração direta, e H3 ficou em
**empate estatístico** com o A2 em fidelidade. Num documento que gasta um
capítulo inteiro recusando-se a exagerar, o resumo era o único lugar que
exagerava.

Três reparos, aplicados nos dois idiomas:

1. Acrescentada a ressalva "ainda que abaixo dos 98,1% da geração direta" e uma
   frase nova: em fidelidade topológica o especializado **empata** com o de
   fronteira e **não alcança** o XML direto.
2. "64,8% contra 98,1% pelos mesmos modelos" citava **um** par e alegava
   replicação em duas famílias. Agora cita os dois pares (64,8%/56,6% contra
   98,1%/94,3%), como já fazia a Conclusão.
3. "esse patamar de validade replicou-se" era generoso: as réplicas deram
   **83,0%**, não 86,8%. Agora o número aparece.

Menores, só no inglês: "more economically in tokens" → "at a lower token cost";
"low-rank adaptation over quantized weights" → "on quantized weights".

Verificação: 90 páginas, zero erro, zero referência indefinida; resumo em ~370
palavras e abstract em ~350, ambos dentro da norma.

**Regra que fica**: o resumo é escrito antes de o capítulo de resultados
estabilizar e não é revisitado quando um desfecho muda. Toda vez que um número
do capítulo 5 mudar, reler o resumo e o abstract **procurando o que eles deixam
de dizer**, não só o que dizem errado.

### Emenda de redação no resumo/abstract (mesma noite)

Rafael levantou, corretamente, que os 64,8% do A2 podiam ser lidos como
resultado *da proposta*, e não da condição por *prompt* — "então o teste dele
ficou 30% pior que XML direto". O texto era preciso ("descrever a linguagem por
prompt", "instruídos pela gramática"), mas o par de maior contorno numérico
(64,8% contra 98,1%) chegava primeiro, e a proposta aparecia depois como "o
modelo pequeno especializado", expressão que nunca a identificava **como** a
proposta.

Duas trocas, sem mover número algum:

- a condição foi para o sujeito da frase da refutação: "fornecer a gramática no
  \textit{prompt} reduziu a confiabilidade: modelos de fronteira **assim
  instruídos**…";
- a proposta passou a ser nomeada: "**A configuração que este trabalho propõe**
  — um modelo pequeno com a notação internalizada por ajuste fino, e não
  descrita no \textit{prompt} — atingiu 86,8%…".

**O que foi recusado, e por quê**: abrir o resumo pelo 86,8%. H1 e H2, as
hipóteses **primárias pré-registradas**, são sobre a condição por *prompt* e
foram refutadas; a do modelo ajustado é a H3, que ficou em empate. Promover a
exploratória a manchete e adiar a refutação da primária seria a única passagem
do documento a fazer o que o pré-registro existe para impedir. A ressalva "ainda
que abaixo dos 98,1%" também fica.

Resumo em ~385 e abstract em ~365 palavras; 90 páginas, zero erro.

---

## 2026-08-31 — Revisão intensiva da Metodologia

Pedido do Rafael: foco total no capítulo 4, revisão individual e remoção de
**todos os travessões**. Eram 71 (50 unicode e 21 em `---`), cerca de um a cada
96 palavras. Nenhum foi trocado mecanicamente por vírgula: cada construção foi
reescrita como dois pontos, parênteses, vírgula ou frase separada, conforme o
papel que o travessão cumpria. **Restam zero.**

A varredura frase a frase encontrou mais do que pontuação.

### Cinco erros factuais

1. **Regra de admissão das referências contradizia o código.** O texto dizia que
   "modelos sem nota atribuída são excluídos"; `run_benchmark.references` admite
   `score IS NULL OR score >= 4`, e **as 53 referências primárias do PMo têm nota
   nula** (conferido no banco). A regra correta, agora escrita: admite-se a
   primária do PMo, que é o gabarito do conjunto, mais as alternativas do Zenodo
   com nota ≥ 4; a exclusão por ausência de nota vale só entre as alternativas.
2. **"dez versões, cada uma executada contra o corpus completo"** — a v1 rodou
   sobre 756 amostras (`dsl_transpiler_runs`). Corrigido para "da segunda versão
   em diante, toda execução cobriu o corpus inteiro".
3. **O split de validação não existia no capítulo.** A conta impressa era
   768 − 18 = 672, que não fecha (dá 750). Faltavam os **78 de validação**,
   justamente o corte que a §5.6.4 diz ter mudado o modelo entregue. Escrito,
   com a razão do agrupamento por documento e o papel de critério de parada.
4. **Orçamento por época: 1,39 M → 1,17 M \textit{tokens}.** Recalculado sobre os
   672 exemplos reais com o tokenizador do modelo base; o valor antigo vinha de
   outro conjunto.
5. **Estatísticas de comprimento de sequência**, todas remedidas e agora
   reproduzíveis: mediana 1.586 → **1.615**, p90 2.725 → **2.753**, máximo
   13.083 → **13.112**, truncados a 1.024 751 → **757**. A medição reproduz
   exatamente o 690/18/672 do log de treino. Os \textit{prompts} fixos passaram
   de 756/1.354 para **753/1.351** (propagado à §5.6.4).

### Duas adições

- **Hiperparâmetros do SFT**, que não constavam em lugar nenhum da monografia:
  posto 16, escala 32, alvo `all-linear`, \textit{dropout} 0,05, LR $10^{-4}$
  com cosseno e aquecimento de 3\%, AdamW 8 \textit{bits} paginado, três épocas,
  lote efetivo 8, \textit{checkpointing} de gradiente, semente 42. Sem isso a
  §4.10 prometia reprodução integral que o texto não permitia.
- **Figura 1, diagrama do protocolo** (`figuras/pipeline.tex`), que era um
  `% TODO` no arquivo desde o início. Mostra as duas fases compartilhando a
  mesma cauda determinística, com borda tracejada para etapa probabilística e
  sólida para determinística: é a afirmação central do capítulo em uma imagem.
  Conferida em renderização, não só em log; a primeira versão estourava a margem.

### Notação e forma

- **Colisão dupla de símbolos**: $R$ era o multiconjunto de referência e $R\!c$
  a revocação; $C$ era o candidato e também um nó no exemplo $A \to \{B,C\} \to D$
  dois parágrafos adiante. Agora os multiconjuntos são $\mathcal{R}$ e
  $\mathcal{C}$ e as medidas são $P$ e $R$, convenção padrão. Lista de símbolos
  atualizada.
- **Títulos numerados espúrios**: os três `\paragraph` da definição da métrica
  rendiam "4.7.2.0.1 Definição." no texto e no sumário. Viraram subseções não
  numeradas. O mesmo defeito existia uma vez no capítulo 5 e foi corrigido junto.
- **"reduziu a folga de 41,5 para 13,2 pontos"** não dizia folga em relação a
  quê. É a distância para a validade plena, entre A3 e A4; escrito assim.
- Frases reescritas por clareza: os princípios de desenho da DSL ("nomes são
  legibilidade e identificadores são referência"), a abertura da subseção de
  leiaute, e a redundância entre "corpus inteiro a cada versão" e a ressalva da v1.

### Verificação

90 páginas, zero erro, zero referência indefinida. Varredura do capítulo por
palavra duplicada, vírgula solta e minúscula após ponto: limpa. Figura conferida
em imagem.

### O que **não** foi feito

Não reconferi as citações do capítulo contra os originais (a conferência de
17/08 cobriu o `.bib`), não mexi na estrutura argumentativa, e a decomposição
"cerca de 600 da descrição e 268 da DSL" foi **removida** em vez de remedida,
por não ser reproduzível com o script atual.
