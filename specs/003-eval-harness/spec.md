# Spec 003 — Harness de Avaliação e Baselines

| Campo | Valor |
|---|---|
| Status | **PRONTA PARA CONGELAR** — bloqueadores fechados em 2026-08-09 |
| Congelar em | commit imediatamente anterior à primeira execução do experimento |
| Commit de congelamento | _(preencher: `git rev-parse HEAD`)_ |
| Data de congelamento | _(preencher)_ |
| Prioridade | 3 (CLAUDE.md) |
| Depende de | `json_to_dsl_v10_en`, `dsl_to_xml_v5_en`, `src.evaluation.topology` |

> **Regra de pré-registro.** Depois de congelado, este documento só muda por
> emenda registrada na seção 9. Alterar definição de métrica, braço ou critério
> de análise **após ver resultados** invalida a comparação. Emendas são
> permitidas; emendas silenciosas não.

---

## 1. Objetivo

Medir se gerar **DSL comprimida + transpilação determinística** produz BPMN
melhor do que gerar **XML BPMN diretamente**, sob o mesmo orçamento de modelo,
contra o gold do PMo Benchmark.

Esta é a evidência central da tese. O harness precisa ser reprodutível por
terceiros a partir do repositório e do `data/dataset.db`.

## 2. Precondições

> ✅ **[Spec 004](../004-camada-de-dados/spec.md) concluída** em 2026-08-09: base
> regenerada em inglês, gold do PMo carregado em `gold_models` (53 referências) e
> `topology.compare_xml` disponível. As precondições deste harness estão satisfeitas.

### Precondições já satisfeitas

Base atual: `json_to_dsl_v10_en` + `dsl_to_xml_v5_en`, 1021 amostras, rótulos em
inglês (conferência registrada na spec 004 §6).

| Precondição | Estado | Evidência |
|---|---|---|
| Transpilação DSL→XML válida | ✅ | XSD 1021/1021 |
| Equivalência topológica JSON↔XML | ✅ | eixo 2: 1017/1021 exatos, df-F1 0,9999 |
| Baseline determinístico JSON→XML direto | ✅ | `src.data.deterministic.json_to_xml` |
| Holdout isolado do treino | ✅ | `split='holdout'` (pmo 53 + zenodo 24 = 77) |

Resíduo do eixo 2: **4 casos não-exatos**, todos só com arestas extras.
`df_missing` está zerado — nenhuma lógica é perdida. Documentar como limitação;
não corrigir durante o experimento.

A troca de gerador ([ADR 0002](../adr/0002-modelo-gerador.md)) expôs três bugs
reais, todos corrigidos e cobertos por teste:
1. splits implícitos descartavam arestas (`graph._normalize_implicit_splits`);
2. `json_to_dsl` não era determinístico entre processos (iteração de `set` sem
   ordenação em `_find_merge_point`);
3. branch vazio de `and` era descartado na emissão do XML, colapsando
   paralelismo em sequência (`transpiler.xml`).

Resultado: `df_missing` foi de 20 casos para zero, superando a base anterior.

## 3. Definições operacionais das métricas

> Cada métrica abaixo estava até aqui registrada **apenas como sigla** no
> CLAUDE.md. As definições desta seção são normativas: o código segue este
> documento, não o contrário.

### 3.1 XSD-Val — validade sintática

Binária, por amostra. `src.transpiler.xsd.validate_bpmn_xsd(xml) == []` contra
`schemas/bpmn20.xsd`. Reportada como taxa sobre o conjunto de avaliação.
Amostra que não valida entra nas demais métricas como **falha total**
(DF-F1 = 0), nunca como dado ausente.

### 3.2 DF-F1 — fidelidade topológica (**métrica primária**)

> Renomeada de "PME-F1" pela [spec 004 §3](../004-camada-de-dados/spec.md): o
> PMo Benchmark tem formato próprio `pme/` (tasks/events/gateways/flows) e
> provavelmente uma métrica homônima. Reservar a sigla evita colisão com
> resultados publicados. O documento usa **DF-F1** em toda parte; "PME-F1" fica
> reservado à métrica do benchmark, caso venha a ser implementada.

F1 sobre o multiconjunto *direct-follows* projetado em nós emitíveis, pulando
gateways de roteamento.

- **Função**: `src.evaluation.topology.compare_xml(gold_xml, candidate_xml)`.
- **Referência**: BPMN lógico do PMo em `gold_models` (53 linhas, carregadas da
  spec 004 §4.3). O gold é XML, não JSON — por isso `compare_xml` e não
  `compare()`, que é a variante JSON↔XML usada no eixo 2 interno.
- **Candidato**: XML gerado pelo braço sob teste.
- **Identidade de nó**: rótulo normalizado; eventos anônimos colapsam para
  `<start>` / `<end>` / `<catch>` / `<throw>`.

Ambas as funções compartilham `xml_direct_follows` e `_prf`, então a projeção é
a mesma nos dois usos. `compare_xml(gold, gold)` é identidade nos 53 (AC-3).

### 3.2b MF-F1 — mensagens entre participantes (**secundária, reportada ao lado**)

F1 sobre o multiconjunto de `messageFlow` `(rótulo_origem, rótulo_destino)`,
via `topology.message_flows`. Extremidades podem ser nós ou participantes.

**Nunca somada ao DF-F1.** `sequenceFlow` é ordem de execução, `messageFlow` é
comunicação — fundir as duas produziria casamento falso, com uma mensagem do
candidato valendo por uma sequência do gold.

**Por que existe.** Sem ela, dois defeitos opostos ficavam invisíveis: um
candidato que modela tudo num pool só é penalizado por não reproduzir a
fragmentação do gold, e um candidato que omite **todas** as mensagens pontua
idêntico a um que as inclui. Verificado no `23.bpmn`: omitir as 6 mensagens
mantém DF-F1 = 1,0 e leva MF-F1 a 0,0.

**Assimetria declarada entre braços.** O transpiler tem código para emitir
`messageFlow` (`xml.py:218`) e a gramática tem `message ... from #a to #b`, mas
**nenhuma das 1021 amostras geradas contém mensagens**. Os braços de DSL, na
prática, não as produzem; os de XML direto podem. Contar mensagens no DF-F1
daria vantagem estrutural a A1/A1g por uma limitação do nosso pipeline, não por
qualidade do modelo — daí a métrica separada, que expõe a diferença em vez de
embuti-la na primária.

**Alcance**: 2 dos 53 itens do holdout têm mensagens no gold (`23.bpmn` com 6,
`38.bpmn` com 4). O `24.bpmn`, que também tem, está entre os dois excluídos.

### 3.3 TCR — razão de compressão de tokens

```
TCR = tokens(XML_lógico) / tokens(DSL)
```

- **> 1 ⇒ a DSL é mais compacta.** Redução percentual derivada: `1 − 1/TCR`.
- Tokenizador: **o do Qwen2.5-Coder-7B**, o mesmo modelo-alvo. Um tokenizador
  diferente muda o número; fica congelado aqui.
- **O XML do denominador é o XML lógico (`--no-layout`).** O BPMNDI infla o XML
  em várias vezes sem conteúdo semântico; medir TCR contra XML com layout
  inflaria artificialmente o resultado principal da tese. Não fazer.
- TCR é **descritiva, não comparativa entre braços**: só existe para braços que
  emitem DSL. Reportar média e IC95% bootstrap.

> ⚠️ Divergência resolvida aqui: o referencial teórico
> (`subsec:tcr`) define TCR como razão XML/DSL (>1 = melhor). Qualquer texto do
> projeto que use a forma de redução `1 − DSL/XML` deve ser corrigido para
> a forma-razão ou marcado explicitamente como "redução".

#### Medição de referência (2026-08-09, base regenerada em inglês)

Medido sobre os 1021 pares `json_to_dsl_v10_en` / `dsl_to_xml_v5_en`,
tokenizador `Qwen/Qwen2.5-Coder-7B`, IC95% bootstrap pareado (10.000, seed 42):

| Denominador | TCR médio | IC95% | Mediana | Redução |
|---|---|---|---|---|
| **XML lógico** (definição normativa) | **6,01** | [5,96; 6,06] | 5,99 | **83,4%** |
| XML com BPMNDI (*não usar*) | 17,24 | [17,10; 17,38] | 17,26 | 94,2% |

O layout quase triplica o TCR sem acrescentar semântica. **83,4% é o número
honesto**; qualquer valor próximo de 94% no texto veio da variante com layout.

A base anterior em português dava 5,08 (80,3%). O inglês é mais compacto por
rótulo, o que explica a diferença; o número válido é o da base atual.

Reproduzir:
```
uv run --with transformers python -m src.evaluation.run_tcr \
  --source-dsl-version json_to_dsl_v10_en --xml-transpiler-version dsl_to_xml_v5_en
```

### 3.4 SA — adequação semântica: **fora da v1**

Cortada em 2026-08-09. Era o único componente não verificável por código, exigia
LLM-juiz com prompt congelado mais 15 itens rotulados à mão para calcular
Cohen's κ, e a própria spec já determinava que **nunca sustentaria conclusão**.
Custo de trabalho manual alto para um número que não entra em nenhuma decisão.

Fica como trabalho futuro. A fidelidade ao texto-fonte que a SA mediria continua
descoberta — isso é limitação a declarar na monografia, não lacuna escondida:
DF-F1 mede estrutura contra o gold, não aderência à descrição original.

### 3.5 Métricas fora da v1

**GED** — cálculo exato é NP-difícil e toda aproximação depende de um modelo de
custo que não está definido no projeto. DF-F1 já mede estrutura. Fica fora da
v1; se voltar, exige emenda com o modelo de custo explícito.

**C/D** — removida em 2026-08-09. A sigla constava apenas da lista de módulos do
CLAUDE.md/AGENTS.md, sem expansão, sem definição no referencial teórico e sem
implementação. Escopo fantasma herdado de rascunho; retirada também dos dois
documentos.

## 4. Desenho experimental

**Conjunto de avaliação:** os 53 processos do PMo (`split='holdout'`).

**Multi-referência do Zenodo.** A fonte traz **223 modelos** em 24 processos
(6 a 12 cada); **222 têm nota** de especialista de 0 a 5 em `*.quality.txt` e
**175 passam no filtro ≥ 4** (3 a 10 por processo). Regra fixada: para cada
candidato, pontuar contra todas as referências com nota ≥ 4 e ficar com o
**máximo**. Mede a alegação correta — o candidato bate ao menos um modelo que um
especialista aprovou — e descarta as variantes reprovadas, inclusive os três
modelos com nota 0.

**Modelo sem nota é descartado.** `M_j01/9.bpmn2.xml` é o único sem
`.quality.txt`; sem evidência de aprovação, fica fora do conjunto de referência.
Três modelos com nota ≥ 4 também caem por não produzirem nenhuma aresta
direct-follows — referência degenerada não serve de referência.

**Estado carregado** (`gold_models`, 2026-08-09): 53 referências primárias do PMo
mais **172 alternativas do Zenodo** cobrindo 24 itens (4 a 11 cada). O
mapeamento Zenodo→PMo é bijeção verificada em carga, derivada por similaridade
de texto contra os 24 itens com `origin='Mangler et al. (2023)'`; o par
`zenodo_G_g01 → pmo_30` casa por eliminação (similaridade 0,09, descrição
reescrita pelo PMo) e está registrado aqui por ser o único frágil.

Reportar quantas referências entraram por item: a ambiguidade de modelagem é
resultado, não ruído.

_(Contagens conferidas em 2026-08-09. A versão anterior desta seção dizia 208
modelos — erro de apuração, corrigido antes do congelamento.)_

**Braços** (todos sobre os mesmos 53 itens, comparação pareada):

| ID | Braço | Modelo | Papel |
|---|---|---|---|
| A1 | SOTA independente → XML direto | `deepseek-v4-pro:cloud` | baseline forte, o que se faz hoje |
| A2 | SOTA independente → DSL → XML | `deepseek-v4-pro:cloud` | isola o efeito da DSL |
| A1g | Gerador → XML direto | `glm-5.2:cloud` | leitura de destilação |
| A2g | Gerador → DSL → XML | `glm-5.2:cloud` | teto que o SFT tenta alcançar |
| A3 | Qwen2.5-Coder-7B base → DSL | local | piso do modelo pequeno |
| A4 | Qwen2.5-Coder-7B SFT → DSL | local | a proposta da tese |

**Por que dois modelos prompted.** O `glm-5.2` gerou o corpus de treino
([ADR 0002](../adr/0002-modelo-gerador.md)), então usá-lo como único baseline
tornaria A4 uma destilação dele — leitura válida, mas que confunde "a DSL ajuda"
com "o aluno imita o professor". O `deepseek-v4-pro` é independente do corpus
atual e dá o baseline limpo; o GLM entra em paralelo para a leitura de
destilação ser reportável.

**Limitação de reprodutibilidade**: a Ollama Cloud não oferece tags datados para
`deepseek-v4-pro` nem `kimi-k2.6` — só `:cloud`, que é alias móvel. Verificado em
2026-08-09. Registrar a data de acesso e declarar que os braços prompted não são
reexecutáveis de forma bit-idêntica; o banco é o registro autoritativo.

A4 depende da prioridade 5 (SFT). A1/A1g/A2/A2g/A3 rodam antes e já sustentam a
comparação DSL vs XML direto; A4 entra como segunda rodada sob o mesmo spec.

**ProMoAI** (Kourani et al. 2024) fica como referência qualitativa de trabalho
relacionado. Reexecutá-lo está fora do escopo v1 — declarar isso no texto em vez
de comparar com números publicados sob protocolo diferente.

## 5. Critérios de aceitação

> ACs descrevem **comportamento do harness**, não resultado do experimento.
> Resultados esperados são hipóteses (seção 6.1) e não viram teste.

Cada AC tem um teste homônimo em `tests/evaluation/test_harness_spec.py`.

| ID | Critério | Teste |
|---|---|---|
| AC-1 | Roda apenas sobre `split='holdout'`; recusa (levanta erro) qualquer `sample_id` presente em `export_training()`. | `test_ac1_refuses_training_samples` |
| AC-2 | XML inválido no XSD produz linha com `xsd_valid=0` e `df_f1=0.0` — nunca linha ausente nem exceção. | `test_ac2_invalid_xml_scores_zero` |
| AC-3 | Determinismo: duas execuções sobre as mesmas entradas produzem linhas idênticas exceto `created_at`. | `test_ac3_rerun_is_deterministic` |
| AC-4 | TCR usa XML **sem** BPMNDI; XML com layout no mesmo processo dá TCR idêntico. | `test_ac4_tcr_ignores_layout` |
| AC-5 | DF-F1 delega a `topology.compare_xml()` sem reimplementar a projeção. | `test_ac5_df_delegates_to_topology` |
| AC-6 | Falha de parse da DSL é registrada como `parse_ok=0` e **não** dispara retry no número principal. | `test_ac6_no_silent_retry` |
| AC-7 | Cada linha grava `arm`, `model_id`, `prompt_version`, `spec_commit`, permitindo rastrear o resultado até este documento. | `test_ac7_provenance_columns_present` |
| AC-8 | Reexecução parcial substitui as linhas do par (braço, versão) em vez de duplicar — mesmo contrato de `run_topology.py`. | `test_ac8_rerun_replaces_rows` |

## 6. Protocolo experimental (pré-registro)

### 6.1 Hipóteses

- **H1 (primária):** A2 ≥ A1 em DF-F1 — gerar DSL não perde fidelidade frente a
  gerar XML direto, com o mesmo modelo.
- **H1g (replicação):** A2g ≥ A1g em DF-F1 — o efeito da DSL se repete com o
  outro modelo prompted. Replicação interna: se H1 vale e H1g não, o efeito é do
  modelo e não da DSL.
- **H2:** A2 > A1 em XSD-Val — a transpilação determinística garante validade que
  a geração direta não garante.
- **H3:** A4 ≥ A2 em DF-F1 — o modelo pequeno finetunado alcança o SOTA prompted
  independente, a custo muito menor.
- **H4 (descritiva):** TCR ≥ 2 nos braços com DSL. _(A medição interna já dá
  6,01 na base de treino; aqui é sobre as saídas dos braços.)_

Resultado contrário a H1/H3 é **resultado publicável** e deve ser reportado como
tal. O spec existe para tornar esse desfecho reportável em vez de tentador de
esconder.

### 6.2 Parâmetros congelados

| Parâmetro | Valor |
|---|---|
| Temperatura | 0,0 (reduz variância; **não** garante determinismo — [ADR 0003](../adr/0003-nao-determinismo-temperatura-zero.md)) |
| Amostras por item (k) | **3**; a unidade de análise é a **mediana por item** |
| Seed | 42 onde aplicável |
| Retries de parse | 0 no número principal |
| `max_tokens` — A1/A1g (emitem XML) | **8192** |
| `max_tokens` — A2/A2g/A3/A4 (emitem DSL) | **2048** |
| Modelo prompted independente | `deepseek-v4-pro:cloud`, acesso em 2026-08-09 |
| Modelo prompted gerador | `glm-5.2:cloud`, acesso em 2026-08-09 |
| Modelo pequeno | `Qwen/Qwen2.5-Coder-7B` |
| Prompts | versionados em `specs/003-eval-harness/prompts/`, hash no banco |

**Os limites de token são deliberadamente diferentes por braço.** Medição sobre
o holdout com o tokenizador do Qwen: a DSL usa no máximo 520 tokens (mediana
217), o XML lógico do gold chega a 4232 (mediana 1918). Um teto único apertaria
A1 e sabotaria o baseline que a tese quer superar; o "mesmo orçamento" de §1 é o
**modelo**, não o teto. Truncamento é registrado por amostra e reportado — nunca
confundido com erro de modelo.

**Volume da primeira rodada**: 5 braços × 53 itens × k=3 = **795 gerações**
(A4 entra depois do SFT, somando 159).

### 6.3 Análise

- **Unidade de análise**: mediana das k=3 execuções por item. A mediana, e não a
  média, porque o ADR 0003 mostrou saídas ocasionalmente degeneradas — uma
  execução que falha o XSD puxaria a média de forma desproporcional.
- Comparações **pareadas** por item (mesmos 53 em todos os braços).
- **Contrastes planejados**, fixados aqui para que a correção múltipla não vire
  pesca: **(1)** A2 vs A1, **(2)** A2g vs A1g, **(3)** A4 vs A2. Holm sobre esses
  três. Qualquer outro par é exploratório e reportado como tal.
- Teste: Wilcoxon signed-rank pareado, α = 0,05, sobre a métrica primária.
- IC95% por bootstrap pareado (10.000 reamostragens, seed 42).
- **Variância intra-braço**: reportar a dispersão entre as k=3 execuções por
  item. É a evidência empírica do ADR 0003 e entra na tese como limitação.
- n = 53 é pequeno: reportar tamanho de efeito e IC, não só p-valor.

### 6.4 Desvios

Qualquer desvio do protocolo durante a execução é registrado na seção 9 com
data, motivo e se ocorreu antes ou depois de observar resultados.

## 7. Invariantes

1. **Holdout nunca entra em treino.** Vale para A4 e para todo SFT futuro.
2. Comparação XML↔XML é sempre topológica + XSD, **nunca igualdade textual**.
3. Resultados vão para `data/dataset.db`, sem JSONL intermediário.
4. Todo número que aparecer na tese tem uma linha correspondente no banco.

## 8. Fora de escopo (v1)

- GED e SA (seções 3.4-3.5) · Reexecução do ProMoAI · Constrained decoding como braço
- Qualidade visual do layout como métrica (BPMNDI é para inspeção humana)
- GRPO (prioridade 6, opcional)

## 9. Emendas e desvios

_(vazio até o congelamento)_

| Data | Item alterado | Motivo | Antes/depois de ver resultados |
|---|---|---|---|

## 10. Questões em aberto — **RESOLVIDAS** (2026-08-09)

Todos os bloqueadores de congelamento foram fechados. Registro das decisões:

| Item | Decisão | Onde |
|---|---|---|
| **C/D** | Removida — sigla sem definição, sem implementação | §3.5 |
| **Modelo prompted** | Dois braços: `deepseek-v4-pro:cloud` (independente) e `glm-5.2:cloud` (gerador) | §4, §6.2 |
| **LLM-juiz (SA)** | Cortado da v1; vira trabalho futuro | §3.4 |
| **`max_tokens`** | 8192 para quem emite XML, 2048 para quem emite DSL — medido, não arbitrado | §6.2 |
| **Multi-referência Zenodo** | Máximo entre referências com nota ≥ 4 | §4 |
| **`k`** | 3, com mediana por item como unidade de análise | §6.2, §6.3 |

**A spec está pronta para congelar.** O congelamento é o commit imediatamente
anterior à primeira execução dos braços; preencher o cabeçalho com hash e data
nesse momento.

Fora de escopo desta spec, mas ainda em aberto no projeto: confirmar no paper do
PMo se existe métrica oficial sobre o formato `pme/` (a sigla PME-F1 foi
reservada por isso) e resolver a atribuição do dataset — o banco diz Kourani
2024, o `.bib` usa `brissard2025pmo`.

## 11. Rastreabilidade

| Artefato | Caminho |
|---|---|
| Este spec | `specs/003-eval-harness/spec.md` |
| Testes de AC | `tests/evaluation/test_harness_spec.py` |
| Métrica topológica | `src/evaluation/topology.py` |
| Runner existente (padrão a seguir) | `src/evaluation/run_topology.py` |
| Harness novo | `src/evaluation/run_benchmark.py` _(a criar)_ |
| Migração da tabela | `src/data/migrations/create_benchmark_eval.py` _(a criar)_ |
| Constituição do projeto | `CLAUDE.md` |
