# Spec 003 — Harness de Avaliação e Baselines

| Campo | Valor |
|---|---|
| Status | 🔒 **CONGELADA** em 2026-08-15 |
| Protocolo congelado no commit | `f24aba57b8a86ff8e5307eba13938391d4dd2cd2` |
| Data de congelamento | 2026-08-15 |
| Tag | `spec-003-frozen` |
| Prioridade | 3 (CLAUDE.md) |
| Depende de | `json_to_dsl_v10_en`, `dsl_to_xml_v5_en`, `src.evaluation.topology` |

> **Regra de pré-registro.** Depois de congelado, este documento só muda por
> emenda registrada na seção 9. Alterar definição de métrica, braço ou critério
> de análise **após ver resultados** invalida a comparação. Emendas são
> permitidas; emendas silenciosas não.

**Estado no momento do congelamento**, verificado e registrado para auditoria:

| Item | Valor |
|---|---|
| `benchmark_eval` | **0 linhas** — nenhum resultado observado |
| Suíte de testes | 290 passando, `ruff` limpo |
| Conjunto de avaliação | 53 itens PMo (`split='holdout'`) |
| Referências | 53 primárias + 172 alternativas do Zenodo (nota ≥ 4) |
| Volume da 1ª rodada | 6 braços × 53 × k=3 = **954 gerações** |

`sha256` dos prompts, que o harness grava por linha (AC-7):

| Prompt | `sha256` |
|---|---|
| `benchmark/xml_direct.md` | `0dbf1e014ff29c0c4365b66ce0c9929634fd6ffbd967c414e7ba71dbde961ddc` |
| `benchmark/dsl_grammar.md` | ~~`59f28d37daefac9c82d4f9e15330a7ae4647b07a430cff474e7cd7512b0774ad`~~ → `c6bb757ea9b1…` (emenda **E-1**, §9) |
| `benchmark/dsl_minimal.md` | `11eaf38e24354cdc17f5b4ab3320bb0d46c066779dadbe889c4efe8c328174b1` |

**O que está congelado**: definição das métricas (§3), braços e regra de
multi-referência (§4), critérios de aceitação (§5), hipóteses (§6.1), parâmetros
(§6.2) e plano de análise (§6.3).

**O que não está**: implementação. Corrigir um defeito do harness e reexecutar
não é emenda — é conserto. Emenda é mudar o que este documento *define*.

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

#### Proveniência — a métrica não é autoral

Registrado aqui para que a monografia não a apresente como invenção. A relação
*directly-follows* é a abstração canônica de process mining: é sobre ela que se
constrói o algoritmo α (van der Aalst, Weijters & Maruster, 2004) e o DFG que
alimenta os mineradores seguintes. Comparar **modelo contra modelo** por pares
adjacentes tem precedente direto:

| Trabalho | Relação com o DF-F1 |
|---|---|
| TAR — Zha et al. (2010) | pares de tarefas adjacentes, com Jaccard; é o parente mais próximo |
| Behavioral profiles — Weidlich, Mendling & Weske (2011) | ordem estrita, exclusividade, interleaving |
| GED — Dijkman et al. (2011) | similaridade estrutural por custo de edição |

Nosso é o **empacotamento**: projeção estrutural sobre BPMN pulando gateways,
F1 sobre multiconjuntos (multiplicidade conta), rótulo como identidade e máximo
sobre multi-referência. Em uma frase: **DF-F1 ≈ TAR com F1 no lugar de Jaccard**.

#### Limitação declarada — estrutural, não comportamental

TAR e behavioral profiles derivam as relações do **comportamento** (reachability)
do modelo; `xml_direct_follows` deriva da **estrutura** do grafo. A diferença é
observável em bloco paralelo `A → {B, C} → join → D`: comportamentalmente B e C
podem ocorrer adjacentes nas duas ordens, então TAR incluiria `(B,C)` e `(C,B)`;
nossa projeção dá `{(A,B), (A,C), (B,D), (C,D)}` e nenhuma das duas.

A escolha é intencional — determinística, custo linear, sem exigir conversão para
rede de Petri sã, e mede se o candidato reproduziu a estrutura que o gold
especifica em vez de premiar intercalações equivalentes. **Consequência que vale
para a tese**: os números não são diretamente comparáveis a resultados publicados
sob formulação comportamental. Dizer isso no texto, não deixar a banca descobrir.

### 3.2a Alinhamento de rótulos — **decidido em 2026-08-15, antes de congelar**

Descoberto ao rodar o primeiro braço de verdade (A3, `pmo_01`): com igualdade
textual de rótulo, **DF-F1 = 0,0000** para uma saída estruturalmente razoável.

| Gold (humano) | Candidato (LLM) |
|---|---|
| `Provide quote` | `Provide Quote` |
| `Place order` | `Place Order` |
| `Collect customer information` | `Collect Information` |

Dois pares diferem **só em capitalização**. O gold do PMo é redigido por humano e
qualquer LLM parafraseia: nenhum braço reproduziria "Guide customer in selecting
product/service" literalmente. Congelar com casamento exato produziria ~0 em
todos os braços e o experimento **não discriminaria nada** — a comparação
central da tese seria vazia.

**Regra congelada.** Normalizar (minúsculas, pontuação → espaço, espaços
colapsados) e alinhar rótulos por Jaccard de tokens **≥ 0,5**, comparando a
estrutura sob esse alinhamento. Emparelhamento **guloso com desempate
determinístico** (`sorted` por similaridade decrescente, depois rótulo), e não
ótimo: métrica pré-registrada precisa ser reproduzível bit a bit, e o ótimo com
empates depende da implementação. Similaridade 1,0 é ordenada primeiro, então
casamento exato sempre tem precedência. Eventos anônimos (`<start>`, `<end>`) só
casam exatamente — são categorias, não texto.

**Duas famílias reportadas, ambas pré-registradas**, para que ninguém escolha a
mais favorável depois de ver os números:

| Chave | O que mede |
|---|---|
| `df_*` | **primária** — estrutura, sob alinhamento de rótulos |
| `df_strict_*` | igualdade textual — estrutura **e** redação |

Precedente: \citeonline{dijkman2011similarity} também estabelece um mapeamento
de nós antes de comparar estrutura. O limiar 0,5 é parâmetro do pré-registro.

**Efeito medido** (A3 sobre `pmo_01`): estrito 0,0000 → alinhado **0,3478**, com
4 pares casados corretamente. **O eixo 2 interno não muda**: os dois lados vêm do
mesmo JSON, o alinhamento é identidade — verificado em 120 amostras, zero
divergência entre as duas famílias, média 1,000000 em ambas.

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

**Como reportar (importante).** Quando gold e candidato não têm mensagem alguma,
MF-F1 = 1,0 por vacuidade — ambos os multiconjuntos são vazios. Isso vale para
51 dos 53 itens, então a **média de MF-F1 sobre o holdout inteiro é enganosa**:
ficaria perto de 1,0 sem que nenhum braço tenha acertado uma mensagem sequer.
Reportar MF-F1 **apenas sobre os itens cujo gold contém mensagens** (n = 2), e
declarar o n. Com n = 2 a métrica é ilustrativa, não inferencial — não entra em
teste estatístico.

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
| A3 | Modelo pequeno + gramática → DSL | local | piso do modelo pequeno |
| A3m | Modelo pequeno + prompt mínimo → DSL | local | **controle de A4** — isola o adapter |
| A4 | Qwen2.5-Coder-7B SFT → DSL | local | a proposta da tese |

**O desenho é fatorial: {modelo} × {formato de saída}.** A2 e A2g **não são
baselines concorrentes** — são a metodologia da tese executada com um modelo caro,
isto é, o **teto** que A4 tenta alcançar a custo muito menor. O único baseline
externo é A1/A1g (XML direto, o que se faz hoje). Daí os contrastes de §6.3:
A2 vs A1 mantém o modelo fixo e varia só o formato, separando "a DSL ajuda" de
"o modelo é bom"; sem esse par, um A4 bom seria ambíguo entre efeito da DSL e
efeito do finetuning.

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

Cada AC tem um teste homônimo em `tests/evaluation/test_harness_spec.py`
(**implementados em 2026-08-15, 14 testes, todos passando**).

Dois ajustes de redação feitos ao implementar, ambos **antes** do congelamento e
portanto edição, não emenda:

- AC-7 falava em `prompt_version`. O concreto é `prompt_name` + `prompt_sha256`:
  o hash identifica o prompt sem depender de alguém lembrar de incrementar uma
  versão, que é o modo de falha clássico dessa coluna.
- AC-4 dizia que XML com layout "dá TCR idêntico", o que só era verdade porque a
  coluna nunca continha layout. Agora é verdade **por construção**: `run_tcr`
  ganhou `strip_di`, que remove `BPMNDiagram` antes de contar. Em produção é
  identidade (nenhuma amostra tem DI) e a TCR segue 6,01 — verificado após a
  mudança. Existe como defesa contra o risco registrado no TODO: se o layout for
  materializado nessa coluna, a métrica inflaria ~3x em silêncio.

| ID | Critério | Teste |
|---|---|---|
| AC-1 | Roda apenas sobre `split='holdout'`; recusa (levanta erro) qualquer `sample_id` presente em `export_training()`. | `test_ac1_refuses_training_samples` |
| AC-2 | XML inválido no XSD produz linha com `xsd_valid=0` e `df_f1=0.0` — nunca linha ausente nem exceção. | `test_ac2_invalid_xml_scores_zero` |
| AC-3 | Determinismo: duas execuções sobre as mesmas entradas produzem linhas idênticas exceto `created_at`. | `test_ac3_rerun_is_deterministic` |
| AC-4 | TCR usa XML **sem** BPMNDI; XML com layout no mesmo processo dá TCR idêntico. | `test_ac4_tcr_ignores_layout` |
| AC-5 | DF-F1 delega a `topology.compare_xml()` sem reimplementar a projeção. | `test_ac5_df_delegates_to_topology` |
| AC-6 | Falha de parse da DSL é registrada como `parse_ok=0` e **não** dispara retry no número principal. | `test_ac6_no_silent_retry` |
| AC-7 | Cada linha grava `arm`, `model_id`, `prompt_name`, `prompt_sha256`, `spec_commit`, permitindo rastrear o resultado até este documento. | `test_ac7_provenance_columns_present` |
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
  Implementada em `run_tcr --arm/--all-arms`, **mesma definição e mesmo módulo**
  da medição do corpus — duas implementações divergiriam e os números deixariam
  de ser comparáveis. Reporta também **tokens emitidos**, que é a grandeza
  econômica de fato: existe em todo braço e é comparável item a item, enquanto a
  TCR só se define onde há representação intermediária. Nos braços de XML direto
  não há compressão a medir, e a razão **não** é reportada como 1,0 — seria
  apresentar uma tautologia como resultado.

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
| Modelo pequeno | `Qwen/Qwen2.5-Coder-7B-Instruct` (Apache 2.0) — **A3 e A4 partem do mesmo** |
| Quantização de **inferência** A3/A4 | **4-bit NF4**, dupla quantização, compute `float16` |
| Attention A3/A4 | `sdpa` (FlashAttention-2 não suporta Turing) |
| Prompts | `configs/prompts/benchmark/`, hash SHA-256 gravado por linha no banco |
| Prompt A1/A1g | `xml_direct.md` (896 tokens) |
| Prompt A2/A2g/A3 | `dsl_grammar.md` (1000 tokens) — carrega a gramática |
| Prompt A4 | `dsl_minimal.md` (392 tokens) — **idêntico ao prompt de treino do SFT** |

**Prompts — escritos e travados por teste em 2026-08-15.** Três, não dois. O
caminho `specs/003-eval-harness/prompts/` que constava aqui foi trocado por
`configs/prompts/benchmark/`: é a convenção do projeto (`load_prompt`), e a
rastreabilidade que a versão anterior queria já vem do hash no banco.

Garantia de justiça do desenho, verificada em
`tests/evaluation/test_benchmark_prompts.py`:

1. Os blocos `<role>`, `<language>`, `<modeling_rules>` e `<output_contract>` são
   **byte-idênticos** nos três. A única diferença permitida é `<output_format>` e
   `<notation_example>`. Instrução de modelagem divergente faria o benchmark
   medir "qual prompt é melhor" em vez de "qual formato é melhor".
2. Os exemplos de notação de `xml_direct.md` e `dsl_grammar.md` são o **mesmo
   processo**, verificado por `compare_xml` (DF-F1 = 1,0, `df_exact`). Nenhum
   braço recebe padrão de modelagem que o outro não recebeu.
3. `xml_direct.md` **proíbe** BPMNDI — o teto de 8192 tokens vai inteiro para a
   lógica, e a métrica ignora layout. A proibição favorece o baseline.
4. `dsl_minimal.md` não contém gramática, e o teste falha se ela vazar.

**Por que o A4 tem prompt próprio.** Restrição dura de SFT: o prefixo de
instrução na inferência tem de ser idêntico ao do treino. E é a tese — carregar
gramática a cada inferência moveria custo da saída para a entrada, que é
justamente o que o trabalho alega resolver.

*Confundimento resolvido em 2026-08-15*: A3 e A4 diferiam em pesos **e** em
prompt. Acrescentado o braço **A3m** — mesmo modelo e mesmo prompt do A4, sem o
adapter —, de modo que **A4 vs A3m isole o ajuste supervisionado** (só os pesos
mudam). A4 vs A3 continua disponível e mede a intervenção inteira; os dois são
exploratórios, nenhum é contraste pré-registrado de §6.3.

**Custo de entrada, medido.** O preâmbulo da DSL custa **+104 tokens** sobre o
prompt de XML (1000 vs 896) — não os ~1000 que uma estimativa inicial supôs, já
que o braço de XML também precisa de especificação de formato. Contra isso, a
economia de saída é de ~1701 tokens por item (medianas do gold: 1918 no XML
lógico, 217 na DSL). O A4 ainda economiza 608 tokens de entrada sobre o A2.
Reportar isso: o argumento econômico precisa ser feito, não assumido.

**Base do modelo pequeno: `-Instruct`, não a base pura** (2026-08-15, ao
implementar a inferência local). Duas razões:

1. **A3 seria um espantalho com a base pura.** O papel do A3 é o piso honesto —
   "o que um modelo pequeno faz com a nossa DSL, sem o nosso treino". Um modelo
   base não segue instrução de forma confiável, então o piso mediria "modelos
   base não seguem instrução" e não "modelos pequenos não dão conta da tarefa".
   Isso **inflaria o ganho atribuído ao nosso SFT** — e um revisor perceberia.
2. **A3 e A4 passam a partir do mesmo ponto.** Com base idêntica, A4 vs A3 isola
   o adapter: os pesos diferem só por ele. Antes difeririam também de base.

Com 768 pares de treino, partir do Instruct também é a escolha mais provável de
funcionar: sobra menos para o modelo aprender. O tokenizador é o mesmo da linha
Qwen2.5-Coder, então **o TCR de 6,01 não é afetado**, e a licença segue Apache 2.0.

*Permanece declarado*: A3 e A4 ainda diferem no **prompt** (`dsl_grammar` vs
`dsl_minimal`), pelas razões do bloco anterior.

**Quantização — decidida em 2026-08-15** (`article/deep-research-report.md`).
4-bit NF4 nos dois braços locais. A restrição que manda é **A3 e A4 na mesma
configuração**: quantização diferente entre eles faria o contraste medir precisão
numérica junto com efeito do finetuning.

A ressalva do relatório contra 7B na 2080 Ti é sobre **treino** ("possible but
fragile", §RTX 2080 Ti) e não nos atinge: o SFT roda em H100 na nuvem e a placa
local só faz **inferência**, para a qual o mesmo relatório classifica 7B 4-bit
como "practical" (5,52 GB medidos em int4). Turing impõe `float16` como dtype de
compute — não há BF16 nativo — e `sdpa` no lugar de FlashAttention-2.

Nota registrada porque remove uma restrição que se supunha existir: o tokenizador
é **idêntico** em toda a linha Qwen2.5-Coder (vocabulário de 151.643 verificado
entre 7B e 1.5B), então **trocar de tamanho dentro da família não invalida o TCR**
congelado no §3.3. Só a troca de família invalidaria.

**Os limites de token são deliberadamente diferentes por braço.** Medição sobre
o holdout com o tokenizador do Qwen: a DSL usa no máximo 520 tokens (mediana
217), o XML lógico do gold chega a 4232 (mediana 1918). Um teto único apertaria
A1 e sabotaria o baseline que a tese quer superar; o "mesmo orçamento" de §1 é o
**modelo**, não o teto. Truncamento é registrado por amostra e reportado — nunca
confundido com erro de modelo.

**Volume da primeira rodada**: 6 braços × 53 itens × k=3 = **954 gerações**
(A4 entra depois do SFT, somando 159). O braço A3m foi acrescentado em
2026-08-15, antes do congelamento, para tornar o contraste A4 vs A3 interpretável.

### 6.3 Análise

- **Unidade de análise**: mediana das k=3 execuções por item. A mediana, e não a
  média, porque o ADR 0003 mostrou saídas ocasionalmente degeneradas — uma
  execução que falha o XSD puxaria a média de forma desproporcional.
- Comparações **pareadas** por item (mesmos 53 em todos os braços).
- **Contrastes planejados**, fixados aqui para que a correção múltipla não vire
  pesca: **(1)** A2 vs A1, **(2)** A2g vs A1g, **(3)** A4 vs A2. Holm sobre esses
  três. Qualquer outro par é exploratório e reportado como tal.
- Teste: Wilcoxon signed-rank pareado, α = 0,05, sobre a métrica primária,
  **bilateral**. As hipóteses são direcionais ("A2 ≥ A1"), mas a alegação é de
  não inferioridade e quem a responde é o **intervalo de confiança**, não a
  lateralidade do teste. Bilateral é o conservador e afasta a suspeita de que a
  direção foi escolhida depois de ver os dados. Diferenças nulas são descartadas
  (`zero_method="wilcox"`) e o número de empates é reportado.
- Implementação: `src/evaluation/run_analysis.py`, **escrito antes de qualquer
  braço rodar**, com 10 testes contra valores calculados à mão.
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

Toda linha acrescentada aqui exige a última coluna preenchida com honestidade:
uma emenda **posterior** à observação dos resultados enfraquece a comparação e
tem de ser declarada como tal na monografia, não escondida.

| Data | Item alterado | Motivo | Antes/depois de ver resultados |
|---|---|---|---|
| 2026-08-16 | `benchmark/dsl_grammar.md`: `59f28d37…` → `c6bb757e…` (+90 tok, +7,1%) | Glosa conceito→keyword no bloco GATEWAYS e explicitação da assimetria de sintaxe de ramificação. Ver E-1 abaixo. | **DEPOIS** — A3 já executado por completo (159 gerações) |

### E-1 — Glosa de gateways no prompt do braço A3/A2/A2g (2026-08-16)

**Defeito.** O bloco `<modeling_rules>`, compartilhado byte a byte pelos três
prompts, é deliberadamente neutro de notação e nomeia os conceitos em vocabulário
BPMN ("exclusive split", "parallel split"). O bloco `GATEWAYS` do prompt da DSL
listava `xor`, `or`, `and` e `event` **sem glosa alguma** ligando keyword a
conceito. Além disso, a sintaxe de ramificação não é uniforme — `and` separa por
`;` e não admite `->` inicial; `xor`/`or`/`event` separam por espaço e exigem
`->` após o colchete — e o prompt exibia as duas formas sem nunca advertir que
uma não generaliza para a outra.

**Verificabilidade sem recurso aos resultados.** Ambos os defeitos se constatam
lendo os artefatos: a ausência de glosa, comparando os dois blocos do prompt; a
assimetria, submetendo seis construções ao parser. Nenhuma das duas constatações
depende de olhar pontuação de braço algum. Este é o critério que separa emenda
legítima de racionalização pós-hoc, e toda emenda futura deve satisfazê-lo.

**Assimetria que o defeito introduzia.** O prompt de XML é autossuficiente sem
glosa porque BPMN está no pré-treino do modelo: "exclusive split" mapeia sozinho
para `exclusiveGateway`. A DSL é notação nova e não tem esse recurso. A omissão
penalizava, portanto, **apenas os braços de DSL** — handicap específico de
formato, exatamente o eixo que o H1 mede.

**Por que a emenda é defensável apesar de posterior aos resultados.** A correção
só pode elevar A3, A2 e A2g. Elevar A3 **encolhe** o ganho aparente do A4 (H2);
elevar A2/A2g **encolhe** a margem da DSL sobre o XML apenas se o ganho vier de
parsing, e em qualquer cenário reduz o espaço para atribuir à DSL um mérito que
era só do prompt. Uma emenda cujo efeito possível é unicamente contrário às
hipóteses do autor não constitui grau de liberdade do pesquisador.

**Resultados descartados (divulgação obrigatória na monografia).** O braço A3 sob
o prompt `59f28d37…` produziu: 159 gerações, 0 erro de geração, 0 truncamento,
27/53 itens com parse válido (50,9%), 26/53 XSD-válidos, DF-F1 mediano por item
**0,0525**, DF-F1 estrito 0,0083, dispersão intra-item 0,0. Modos de falha:
26/26 `UnexpectedCharacters`, com `parallel`/`parallel_split` (6) e `choice` (3)
entre as keywords inventadas. Estas linhas foram removidas de `benchmark_eval` e
o braço foi reexecutado sob `c6bb757e…`. **Os dois valores devem ser reportados
lado a lado na monografia**; suprimir o primeiro converteria esta emenda em
exatamente o viés que ela pretende corrigir.

**Resultado após a emenda (2026-08-16, prompt `c6bb757e…`).** 159 gerações, 0
erro, 0 truncamento, **31/53** com parse válido, **31/53** XSD-válidos, DF-F1
médio das medianas por item **0,0666**.

| | antes `59f28d37…` | depois `c6bb757e…` |
|---|---|---|
| parse válido | 27/53 | **31/53** |
| XSD válido | 26/53 | **31/53** |
| DF-F1 (média das medianas) | 0,0525 | **0,0666** |
| keywords inventadas `parallel` / `choice` | 7 / 2 | 5 / 2 |

**Leitura.** A correção melhorou pouco: +4 itens de parse e +0,014 de DF-F1, e as
keywords inventadas **não desapareceram**. O gargalo do A3 é, portanto,
capacidade do modelo de 7B, não redação do prompt. Isso reforça a motivação do
SFT por mérito próprio, e não por handicap induzido — que era precisamente a
dúvida que a emenda existia para dissipar. Registrar assim na monografia: a
emenda não salvou o A3, e é isso que a torna informativa.

**Escopo.** `xml_direct.md` (`0dbf1e01…`) e `dsl_minimal.md` (`11eaf38e…`)
permanecem com sha inalterado. Logo A1, A1g, A3m e A4 não são afetados, e a
execução do A3m em curso na data da emenda continua válida.

**Nota de contagem de tokens.** A tabela de estado do congelamento registrou
1000 tokens para `dsl_grammar.md`; a medição feita nesta emenda dá 1264 para o
mesmo arquivo (sha idêntico). A divergência é de **método de contagem**, não de
conteúdo. Os números de custo reportados na monografia devem usar uma única
medição, declarada, e não a tabela do congelamento.

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

Fechados depois, ainda antes do congelamento (2026-08-15): prompts dos três
tipos de braço · alinhamento de rótulos (§3.2a) · quantização e modelo pequeno
`-Instruct` (§6.2) · braço de controle A3m (§4) · lateralidade do teste (§6.3).

**🔒 Congelada em 2026-08-15.** Daqui em diante, mudança só por emenda na §9.

Fora de escopo desta spec, mas ainda em aberto no projeto: confirmar no paper do
PMo se existe métrica oficial sobre o formato `pme/` (a sigla PME-F1 foi
reservada por isso) e resolver a atribuição do dataset — o banco diz Kourani
2024, o `.bib` usa `brissard2025pmo`.

## 11. Rastreabilidade

| Artefato | Caminho |
|---|---|
| Este spec | `specs/003-eval-harness/spec.md` |
| Testes de AC | `tests/evaluation/test_harness_spec.py` |
| Prompts dos braços | `configs/prompts/benchmark/` |
| Invariantes dos prompts | `tests/evaluation/test_benchmark_prompts.py` |
| Métrica topológica | `src/evaluation/topology.py` |
| Runner existente (padrão a seguir) | `src/evaluation/run_topology.py` |
| Harness novo | `src/evaluation/run_benchmark.py` _(a criar)_ |
| Migração da tabela | `src/data/migrations/create_benchmark_eval.py` _(a criar)_ |
| Constituição do projeto | `CLAUDE.md` |
