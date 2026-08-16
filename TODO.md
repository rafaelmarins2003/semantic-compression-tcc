# TODO — roteiro de execução

Atualizado em 2026-08-09. Specs em `specs/`; decisões de alcance amplo em `specs/adr/`.

## Estado atual

**Base ativa**: `json_to_dsl_v10_en` + `dsl_to_xml_v5_en` — 1021 amostras em inglês,
XSD 1021/1021, DF-F1 0,9999, TCR 6,01 (83,4% de redução).

> Corrigido em 2026-08-15: os defaults de `run_tcr.py` apontavam para a base PT
> antiga (`v8`/`v3`), então o comando documentado media o corpus obsoleto e
> imprimia **5,08** em vez de 6,01. Ao trocar a base ativa, atualizar as duas
> constantes no topo do módulo — o número vai para a monografia.

**Métricas** (definidas em [spec 003](specs/003-eval-harness/spec.md) §3): **DF-F1**
projeta o processo no multiconjunto de pares `(a, b)` "a é diretamente seguida por
b", pulando gateways — mede ordem do trabalho, não escolha de encoding. **MF-F1** faz
o mesmo sobre `messageFlow` (comunicação entre pools) e é **reportada ao lado, nunca
somada**. **TCR** = tokens(XML lógico)/tokens(DSL). **XSD-Val** = validade sintática.

**Pronto e verificado**
- DSL + parser (Lark), transpiler DSL→XML, `json_to_xml` direto, layout/BPMNDI
- Fases 1, 2 e 3 concluídas (estrutura, seleção de modelo, regeneração)
- Fundamentação Teórica: 14 páginas escritas (`article/cadeira_tcc/referencial_teorico/`)
- Introdução: escrita no template oficial; bibliografia oficial com 47 entradas

**Decidido**
- [ADR 0001](specs/adr/0001-idioma-dos-artefatos.md) — artefatos em inglês; monografia em português
- [ADR 0002](specs/adr/0002-modelo-gerador.md) — `glm-5.2:cloud` como gerador
- [ADR 0003](specs/adr/0003-nao-determinismo-temperatura-zero.md) — temperatura 0 não é determinística
- [ADR 0004](specs/adr/0004-estrategia-de-dados.md) — medir antes de coletar; treino é 95,3% GitLab

---

## Fase 1 — Estrutura ([spec 005](specs/005-estrutura/spec.md)) — **CONCLUÍDA**

- [x] Achatado `src/data/manipulation/*` e `src/data/ingestion/*` (profundidade ≤ 3)
- [x] `run_*` padronizado para jobs de lote; `import_*` mantido na ingestão
- [x] `run_materialize`: popula `samples.dsl/xml/bpmn_json/parse_ok/xsd_ok`
- [x] Retomada de `preprocess` filtrando por `prompt_version` (bug E4)
- [x] Comandos atualizados no CLAUDE.md e README

## Fase 2 — Seleção do modelo gerador — **CONCLUÍDA**

- [x] Prompts traduzidos para inglês, com diretiva `<language>` explícita
      (`preprocess_process_v2_en`, `bpmn_json_generator_v2_en`)
- [x] Piloto sobre 50 amostras estratificadas × 3 configurações
- [x] [ADR 0002](specs/adr/0002-modelo-gerador.md) — **glm-5.2:cloud** nos dois estágios
- [x] [ADR 0003](specs/adr/0003-nao-determinismo-temperatura-zero.md) — temperatura 0
      não garante determinismo; `k=1` da spec 003 §6.2 fica em aberto

## Fase 3 — Regeneração em inglês — **CONCLUÍDA** (2026-08-09)

- [x] Estágio 1 `run_preprocess`: 1021/1021
- [x] Estágio 2 `run_generate_json` (glm-5.2): 1021/1021 — 1 falha real de modelo (0,1%)
- [x] `json_to_dsl_v10_en`: 1021/1021 · `dsl_to_xml_v5_en`: 1021/1021 com XSD válido
- [x] `run_materialize`: 1021/1021
- [x] Conferência manual de idioma — aprovada (spec 004 §6)
- [x] Três bugs corrigidos, todos cobertos por teste:
      split implícito descartando arestas · `json_to_dsl` não determinístico entre
      processos · branch vazio de `and` descartado no XML. `df_missing`: 20 → **0**

Números da base atual:

| Métrica | Base PT (antiga) | **Base EN (atual)** |
|---|---|---|
| TCR | 5,08 (80,3%) | **6,01 (83,4%)** |
| DF exatos | 1015/1021 | **1017/1021** |
| DF-F1 médio | 0,9999 | **0,9999** |
| XSD | 1021/1021 | **1021/1021** |

## Fase 4 — Camada de dados ([spec 004](specs/004-camada-de-dados/spec.md))

- [x] Gold do PMo carregado em `gold_models` — 53/53, idempotente
- [x] Multi-referência do Zenodo — 172 alternativas (nota ≥ 4) sobre 24 itens
- [x] `compare_xml(gold, cand)` em `src/evaluation/topology.py`
- [x] MF-F1 separado para `messageFlow` (spec 003 §3.2b)
- [x] AC-1 a AC-3 (`tests/evaluation/test_gold.py`)
- [x] AC-4 a AC-7 (`tests/data/test_persistence.py`) — `export_training` agora
      **recusa** `split='holdout'` em vez de entregar o conjunto de avaliação

**Fase 4 concluída.** `gold_models` com 53 referências; `compare_xml` disponível;
todos os 7 ACs da spec 004 cobertos por teste.

## Fase 5 — Harness de avaliação ([spec 003](specs/003-eval-harness/spec.md))

- [x] Bloqueadores §10 fechados (2026-08-09): C/D removida · dois braços prompted
      (`deepseek-v4-pro` independente + `glm-5.2` gerador) · SA cortada da v1 ·
      `max_tokens` 8192/2048 medido · Zenodo = máx entre refs nota ≥ 4 · k=3

Ainda mexem no pré-registro (fazer **antes** de congelar):

- [x] **Prompts dos braços — escritos** em 2026-08-15, em `configs/prompts/benchmark/`.
      **Três, não dois**: `xml_direct.md` (A1/A1g, 896 tk) · `dsl_grammar.md`
      (A2/A2g/A3, 1000 tk, carrega a gramática) · `dsl_minimal.md` (A4, 392 tk, sem
      gramática — **é também o prompt de treino do SFT**, e tem de continuar sendo).
      Justiça travada por teste (`tests/evaluation/test_benchmark_prompts.py`, 12):
      blocos de instrução byte-idênticos entre os três, e os exemplos de notação do
      XML e da DSL provados o **mesmo processo** via `compare_xml` (DF-F1 = 1,0).
      Custo de entrada medido: o preâmbulo da DSL é só **+104 tokens** sobre o de
      XML — a objeção "a DSL empurra custo para a entrada" é quase nula frente aos
      ~1701 tokens de saída economizados por item.
- [x] Corrigido §6.2/§11: caminho dos prompts é `configs/prompts/benchmark/`
      (convenção do projeto, via `load_prompt`), não `specs/003-eval-harness/prompts/`.
- [x] **A4 vs A3 isolado** — braço **A3m** acrescentado em 2026-08-15 (aval do
      Rafael): mesmo modelo e mesmo prompt do A4, sem o adapter. A4 vs A3m isola o
      ajuste supervisionado; A4 vs A3 segue disponível e mede a intervenção
      inteira. Ambos exploratórios. Primeira rodada passa a **954 gerações**.
- [x] **Quantização — decidida** em 2026-08-15: **4-bit NF4**, `float16` de compute,
      `sdpa`. Registrada no §6.2. Base: `article/deep-research-report.md`. A ressalva
      do relatório contra 7B na 2080 Ti é sobre **treino** e não nos atinge (SFT em
      H100; a placa local só infere, e para inferência ele classifica 7B 4-bit como
      "practical", 5,52 GB em int4). Restrição que manda: **A3 e A4 na mesma**.

Implementação sob spec fixa:

- [x] **Inferência local do Qwen** — `src/evaluation/local_model.py`, 2026-08-15.
      4-bit NF4 + dupla quantização, `float16`, `sdpa`, decodificação gulosa com
      semente 42. Cache do modelo por processo (`lru_cache`): carregar 7B leva ~1
      min e o braço faz 159 gerações — sem cache a carga dominaria o experimento.
      Deps pesadas em import tardio, então `--dry-run` e a suíte não exigem torch.
      Ligado ao `run_benchmark` pelo `backend="local"`; adapter LoRA opcional serve
      o A4 depois. `uv sync --extra training` (torch 2.11+cu130, bnb 0.49, peft 0.18).
- [x] **Modelo confirmado pelo Rafael em 2026-08-15**: A3/A3m/A4 usam
      `Qwen2.5-Coder-7B-Instruct`, não a base pura. Com a base, o A3 mediria
      "modelos base não seguem instrução" em vez de "modelo pequeno sem o nosso
      treino", **inflando o ganho atribuído ao SFT**. Efeito colateral bom: A3 e A4
      partem do mesmo ponto, então diferem só pelo adapter. Tokenizador idêntico ⇒
      **TCR 6,01 intacto**. Registrado no spec §6.2 e na Metodologia.
- [x] Migration `create_benchmark_eval.py` + `run_benchmark.py` — 2026-08-15.
      Tabela com uma linha por (braço, amostra, repetição); mediana por item é
      calculada na leitura, nunca gravada, para não esconder a dispersão que o
      ADR 0003 exige reportar. **Duas fases separadas**: `generate` (rede, cara,
      não determinística) e `score` (local, determinística, `--rescore`) — é a
      separação que torna o AC-3 satisfazível. Retomada por (sample_id, rep) e
      `--restart`, no mesmo contrato do `run_model_pilot`.
      Verificado sem rede: gold contra si mesmo dá DF-F1 1,0; XML malformado dá
      0,0 com linha gravada (AC-2); multi-referência resolve 11 refs no pmo_39.
      `strip_fence` normaliza cerca markdown **igual em todos os braços** — sem
      isso a métrica mediria aderência à instrução, com viés a favor do XML.
- [x] `tests/evaluation/test_harness_spec.py` (AC-1 a AC-8) — 2026-08-15, 14 testes.
      Duas mudanças no harness saíram daí, porque os ACs pediam garantia que o
      código ainda não dava:
      · **AC-1** ganhou `assert_holdout_only`, que *levanta erro* em vez de só
        filtrar — rede de segurança se alguém mexer em `EVAL_SOURCE` ou no split.
      · **AC-4** ganhou `strip_di` no `run_tcr`: a TCR passou a ser invariante a
        BPMNDI *por construção*, não por acidente da coluna estar limpa. Em
        produção é identidade e **o TCR segue 6,01** (reconferido).
      Dois ajustes de redação no spec, pré-congelamento: `prompt_version` virou
      `prompt_name`+`prompt_sha256` (hash não depende de alguém lembrar de
      incrementar), e o AC-4 passou a descrever invariância real.
- [x] 🔴 **Casamento de rótulos — resolvido em 2026-08-15.** Achado ao rodar o
      primeiro braço real: com igualdade textual, **DF-F1 = 0,0000** numa saída
      estruturalmente razoável (`Provide quote` vs `Provide Quote` — só a caixa).
      O gold é humano, o candidato é parafraseado por LLM: congelar assim daria ~0
      em **todos** os braços e o experimento não discriminaria nada.
      Regra congelada (spec §3.2a): normaliza + alinha por Jaccard de tokens ≥ 0,5,
      guloso com desempate determinístico. Reporta **duas** famílias
      pré-registradas — `df_*` (alinhado, primária) e `df_strict_*` (textual) —
      para ninguém escolher a mais favorável depois de ver os números.
      Efeito medido: 0,0000 → **0,3478**. **Eixo 2 intacto** (alinhamento é
      identidade; 120 amostras, zero divergência). 6 testes novos.
- [ ] **Reportar MF-F1 só sobre itens cujo gold tem mensagem** (n=2). Nos outros 51
      ambos os multiconjuntos são vazios e o F1 dá 1,0 por vacuidade — a média
      sobre o holdout inteiro ficaria perto de 1,0 sem ninguém acertar mensagem
      nenhuma. Com n=2 é ilustrativa, não entra em teste estatístico.
- [x] **`configs/prompts/` saiu do `.gitignore`** — corrigido pelo Rafael em
      2026-08-15. Os prompts do benchmark e os de construção do corpus passam a ser
      versionados, restaurando o §1 ("reprodutível por terceiros"), o §6.2 e a
      cadeia do AC-7. Falta `git add configs/`.
- [x] **Análise estatística — `src/evaluation/run_analysis.py`**, 2026-08-15,
      **escrita antes de qualquer braço rodar**, que é o ponto: análise redigida
      depois de ver os números pode ser ajustada a eles. Wilcoxon pareado
      bilateral, Holm sobre os 3 contrastes planejados, IC95% por bootstrap
      (10.000, seed 42), efeito rank-biserial e contagem de empates.
      Exploratórios (A4vsA3m, A4vsA3, A3vsA3m) reportados **sem** correção e
      rotulados não confirmatórios. 10 testes contra valores calculados à mão.
      Nova dep: `scipy` — justificada no `pyproject.toml`.
      Lateralidade **bilateral** registrada na §6.3: as hipóteses são direcionais,
      mas quem responde não inferioridade é o IC, não a lateralidade.
- [x] **TCR por braço** — `run_tcr --arm A2` / `--all-arms`, 2026-08-15. Ficou no
      **mesmo módulo** da medição do corpus de propósito: duas implementações da
      mesma métrica divergiriam e os números deixariam de ser comparáveis.
      Reporta **tokens emitidos** (grandeza econômica, existe em todo braço,
      comparável item a item) e a TCR só onde há representação intermediária —
      braço de XML direto não tem compressão a medir, e reportar 1,0 seria
      apresentar tautologia como resultado. 4 testes.
      Verificado com dados reais do A3: mediana 164,5 tokens emitidos, TCR 8,03.
- [ ] **Congelar a spec** (commit datado) e só então rodar A1, A1g, A2, A2g, A3 — 795 gerações

## Fase 6 — Monografia

Capítulos escritos são **documentos vivos**: atualizar conforme o projeto avança.
Marcador `% ATENÇÃO (nota de trabalho...)` no topo de cada `.tex` já escrito.
Compilação verificada em 2026-08-15: 67 páginas, zero citação/referência indefinida.

- [x] Metodologia — reescrita em 2026-08-15 a partir das specs 003/004. Acrescentadas
      as seções de delimitação do problema (marcação verbosa; BPMN como caso),
      pré-registro, seleção do gerador, idioma dos artefatos, DF-F1 com proveniência
      e limitação estrutural, MF-F1, TCR, multi-referência, os 6 braços e a análise
      estatística. Corrigidas 4 defasagens: Kimi+DeepSeek → gerador único (ADR 0002),
      GED removida (fora da v1), 3 baselines → 6 braços, exemplo de DSL em pt → en.
- [x] Resultados — escrito com os números medidos; seção comparativa é placeholder
      declarado até os braços rodarem. Inclui a trajetória entre versões e a análise
      do resíduo (as 4 não-exatas têm `df_missing` vazio: só arestas extras).
- [x] Trabalhos Relacionados — escrito. Substituiu o lipsum do TCC-exemplo. Cinco
      eixos: ProMoAI · representações compactas (**Brissard et al. 2025**) ·
      compressão de entrada vs saída (LLMLingua/Headroom) · SLMs · decodificação
      restrita.
- [x] Atribuição do PMo — **resolvida**. O README do dataset pede citar o paper
      `brissard2025pmr` ("What is the Best Process Model Representation?", AI4BPM @
      BPM 2025). "Kourani 2024" no banco não está errado: é o PMo Benchmark, que é
      só os pares 01–20. Ambas as entradas agora no `.bib`.
- [ ] Migrar Fundamentação Teórica do `referencial_teorico` para o template oficial
- [ ] Conclusão — após a Fase 5
- [ ] Substituir lista de siglas do template-exemplo (hoje é do TCC de saúde) por
      BPMN, DSL, LLM, XSD, TCR, DF-F1, MF-F1
- [ ] Corrigir `\imprimirglossario` (`main.tex:214` usa `\glossarystyle`, removido no
      glossaries v4). Os `\Gls{braile}`/`\Gls{borboleta}` do template-exemplo saíram
      junto com o lipsum de Trabalhos Relacionados.
- [ ] Conferir no PDF original as entradas `.bib` marcadas `% [conferir]`
      (zha2010tar, weidlich2011behavioral, dijkman2011similarity, kopke2024efficient,
      volter2024generative) — veículo/páginas preenchidos sem consultar o original.

### Decisão de escopo em aberto — braço de representação compacta

`brissard2025pmr` compara 9 representações de processo para geração com LLM **no
mesmo dataset que usamos como holdout**, várias criadas para reduzir tokens
(JSON branches, Simplified XML, PME). Não invalida a tese — a pergunta deles é
"qual notação modela melhor por prompt", a nossa é "comprimir a saída e expandir
deterministicamente torna viável gerar marcação verbosa com modelo pequeno" —, e o
posicionamento já está escrito no capítulo.

Fica a decisão: vale acrescentar um braço **SOTA → JSON branches → BPMN**, para
comparar contra a melhor representação compacta existente e não só contra XML
direto? Fortaleceria bastante o resultado; custa +159 gerações e um conversor novo.

## Fase 7 — SFT e publicação

### Oráculo do pipeline — teto medido antes do SFT (2026-08-16)

A DSL do próprio pipeline para os 53 itens do PMo, pontuada contra o gold pela
métrica dos braços, dá **DF-F1 0,1236** — abaixo do A1 (0,1942) e do A2 (0,1375).
Isto é, **um modelo que aprendesse o treino com perfeição ainda perderia para o
baseline**. É o teto da H3 imposto pelos dados, não pelo modelo.

Três causas foram investigadas e **descartadas**:

| hipótese | medição | veredito |
|---|---|---|
| conversor perde paralelismo | JSON 68% → DSL 66% no PMo | falso (perda residual) |
| rótulos derivam do texto por 2 saltos de LLM | ancoragem 62,1% vs gold 60,8%, A1 60,4% | falso (somos os mais ancorados) |
| estrutura subdimensionada | arestas 14 vs gold 18; A1 tem 12 | falso (somos os mais próximos) |

Resta a **escolha lexical**: pipeline e especialista tiram nomes diferentes do
mesmo texto, ambos legítimos, e o DF-F1 pontua isso como erro estrutural. Não
isenta o pipeline — os braços prompted alinham melhor (40–49% vs 32,3%) sobre o
mesmo texto — mas realoca o problema: **não é volume nem estrutura, é
convergência de nomenclatura**.

Consequência para a pergunta "scrape mais dados?": **não resolveria**. Mais
amostras pelo mesmo pipeline não movem o teto. Antes de investir em volume, subir
o alinhamento de rótulos é o que tem efeito direto no teto.

Viés colateral registrado: o pipeline põe raias em **100%** das amostras, o gold
usa em **3/53**. Não afeta DF-F1 (raias não alteram precedência), mas é estilo
herdável pelo SFT.

### Teto humano da métrica — DECIDIDO: não atacar rótulos nem topologia (2026-08-16)

Referências múltiplas do Zenodo (24 itens, 4–11 modelos do mesmo processo)
permitem medir a concordância **entre especialistas**, com a régua idêntica à
dos braços:

| limiar Jaccard | teto humano | A1 | oráculo do pipeline |
|---|---|---|---|
| 0,50 (congelado) | 0,1449 | 0,2070 (143%) | 0,1533 (106%) |
| 0,01 (estrutura pura) | 0,2734 | 0,3940 (144%) | 0,3419 (**125%**) |

Alinhamento de rótulos: humano vs humano **31,0%**, nosso pipeline **32,3%**.

**Estamos acima do teto humano nos dois eixos.** Logo:

- **Rótulos**: nada a corrigir, já estamos na faixa de variação humana.
- **Topologia**: melhoria seria **inverificável**, não apenas cara. "Melhor" só
  se define como concordância com uma referência, e já superamos a concordância
  que as referências têm entre si. Como todo o gold é holdout, qualquer ajuste
  seria contaminação disfarçada de melhoria.
- **Volume**: não move um teto que não é imposto pelos dados.

O limitante é a **métrica**, não o pipeline: DF-F1 contra referência única satura
perto do ruído numa tarefa sem resposta única. Isso é achado da tese, com número.

### Onde ainda há folga real

1. **Validade sintática** — A2 64,8%, A3 58,5%, A1 98,1%. Resposta certa existe,
   folga é grande, e nada do que medimos prevê o resultado do SFT aqui.
2. **Custo** — 138 tokens vs 631.

Pergunta reformulada da H3: *um 7B finetunado atinge validade e fidelidade dentro
da faixa de concordância humana emitindo 1/5 dos tokens, sem modelo de fronteira?*

### Plano se o SFT decepcionar

Diagnosticar **qual** eixo falhou antes de agir:

| sintoma | ação | por quê |
|---|---|---|
| parse baixo | curva de aprendizado (25/50/100% dos dados) | decide se volume é o gargalo, sem tocar holdout |
| parse baixo + curva saturada | **GRPO só com recompensa verificável** (r_sint + r_comp) | não precisa de dado novo; a recompensa é uma chamada ao parser |
| parse bom, DF-F1 baixo | **nada** — reportar | métrica saturada, já estamos no teto humano |
| qualquer | topologia | **nunca**, salvo se conseguirmos referência fora do holdout |

GRPO antes de mais dados: a recompensa `r_sint` é verificável por código e ataca
exatamente o gargalo medido. Descartar `r_topo` do peso — otimizá-la é ajustar à
referência. `r_sem` continua sendo a parte frágil (não verificável).

- [ ] **CORRIGIR `seq 1024` antes de treinar.** Medido em 768 pares com o
      tokenizador do Qwen2.5-Coder: exemplo mediano tem **1.586 tokens**
      (prompt fixo 756 + texto 600 + DSL 268), p90 2.725, max 13.083.
      `seq=1024` trunca **751/768 (98%)**, e o corte é no fim — ou seja, no alvo.
      `seq=2048` trunca 24%; **`seq=4096` trunca 2%**. Usar 4096 e descartar ou
      truncar explicitamente os 18 restantes. Orçamento: **1,39 M tokens/época**.
- [ ] SFT sobre o pool exato regenerado (QLoRA 4-bit NF4, `all-linear`, checkpointing)
      Hiperparâmetros de partida em `article/deep-research-report.md`; para 7B:
      r=8–16, alpha 16–32, dropout 0.05, LR 5e-5–1e-4, 2–4 épocas, **seq 4096**
      (o relatório sugeria 1024; medido, truncaria 98% — ver item acima),
      AdamW 8-bit paged. Em H100 dá para começar em BF16 LoRA e só quantizar se
      precisar — a placa local não é o gargalo do treino.
- [ ] **Separar split de validação antes do SFT.** Hoje só existem `sft`/`grpo`/
      `holdout`; não há conjunto de parada. O relatório é explícito: com corpus
      pequeno a perda de treino não serve de critério de parada, e o checkpoint
      deve ser escolhido por taxa de acerto em validação retida. Cortar do `sft`,
      **agrupando por seção/documento de origem** — 95,3% do treino é do mesmo
      handbook e seções templatizadas vazariam entre treino e validação num corte
      aleatório. Não afeta o holdout (fontes distintas), afeta a escolha de época.
- [ ] Anotar que o pool de treino (768 pares de alta confiança) é ~38% das ~2.000
      amostras que o relatório assume nas suas estimativas. Overfitting é o risco
      dominante, não subajuste — ver [ADR 0004](specs/adr/0004-estrategia-de-dados.md).
- [ ] Publicar dataset + adapter no HuggingFace: model card, datasheet, splits, licença, script de exportação
- [ ] GRPO — opcional, fora do escopo mínimo

---

## Layout / BPMNDI — sob demanda, fora do pipeline

Decidido em 2026-08-08: o layout **não** é materializado no banco. `run_dsl_to_xml`
grava XML lógico; `add_layout` é aplicado só na hora de exportar para inspeção
visual ou via `json_to_xml` (baseline direto).

Motivo: BPMNDI triplica o XML, não alimenta métrica nenhuma (TCR exige XML
lógico por definição normativa, DF-F1 projeta topologia, o gold do PMo é
`bpmn_process` sem DI) e guardá-lo criaria a chance de alguém medir contra a
coluna errada — que é exatamente o erro dos 91% já corrigido.

Se um dia for materializado, tem de ser em **coluna separada**, nunca
sobrescrevendo o XML lógico, senão o AC-4 da spec 003 quebra.

- [x] Branches paralelos vazando da raia — corrigido em 2026-08-08: altura de raia
      passou a ser dimensionada pelo empilhamento real, com topos cumulativos.
      Coberto por `test_parallel_branches_stay_inside_their_lane`.
- [x] Centralização vertical — corrigida em 2026-08-08: nós são centrados na faixa
      do slot, então eventos e tasks compartilham o mesmo centro e as arestas saem
      retas. Coberto por `test_nodes_of_different_sizes_share_a_vertical_center`.

## Em aberto (sem data)

- **Modelo base**: Qwen2.5-Coder-7B está datado; há coders pequenos melhores hoje.
  **Correção (2026-08-15)**: trocar *não* invalida necessariamente o TCR. O
  tokenizador é idêntico em toda a linha Qwen2.5-Coder (vocabulário 151.643,
  verificado entre 7B e 1.5B), então mudar de **tamanho** dentro da família preserva
  os 6,01; só mudar de **família** invalidaria. Consequência: dá para reportar 1,5B
  e 7B lado a lado sem tocar em métrica congelada — e o `deep-research-report.md`
  recomenda justamente 1,5B como modelo de partida para hardware de 11 GB.
- **PME-F1**: nome reservado para a métrica do benchmark sobre `data/raw/pmo/pme/`.
  Confirmar no paper do PMo antes de comparar com resultados publicados.

PS: sempre que terminar o dia, deixar o TODO atualizado para não perder o ponto
de retomada.
