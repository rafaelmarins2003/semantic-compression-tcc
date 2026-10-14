# Mapa de mudanças — 2026-10-12

Inventário do que mudou hoje (código, dados, resultados) e de onde isso toca a
monografia, capítulo por capítulo. Serve de roteiro para a revisão do texto.
Detalhe técnico e números completos: `docs/registro-tecnico.md`, entradas de
2026-10-12.

Caminho da monografia abreviado como `tex/` =
`article/Atualização Template TCC Unifor 2022.2/elementos-textuais/`.

---

## Parte A — O que mudou no projeto

### A.1 Linguagem e transpilador
| mudança | onde | efeito |
|---|---|---|
| Referência por rótulo: `ref: "#" (CNAME \| NAME)` | `src/dsl/grammar.lark` | `#"Rótulo"` aponta para nó já emitido; `#id` continua valendo |
| Leitura da referência por rótulo (slug) | `src/transpiler/xml.py`, `_ref_name` | resolve via `slug_ids`; só para trás |
| Rótulo também resolve em `message ... from #"X"` | `src/transpiler/xml.py`, exportação de `global_refs` | corrige `sourceRef` solto que o XSD aceitava |
| Especificação alinhada à gramática | `src/dsl/dsl_documentation.txt` | ordem `start:kind "Nome"`, `[:message("x")]`, `and` com ramo vazio; `grammar.lark` declarada normativa |

**Compatibilidade verificada:** os 1021 do corpus geram XML byte a byte idêntico
ao de HEAD; as saídas já gravadas de A2 e A4 dão o mesmo resultado (103 e 138).
Não há duas notações: é a mesma, com uma alternativa a mais. **Nada precisa ser
retreinado.**

### A.2 Prompts e braços
| mudança | onde |
|---|---|
| Novo prompt `dsl_grammar_labelref.md` (sha `b49d66cbcc41`): bloco de referências por rótulo e duas imprecisões corrigidas; resto idêntico ao do A2, cabeçalho incluído | `configs/prompts/benchmark/` |
| Novo braço `X-a2r` (DeepSeek V4 Pro, mesmo teto do A2) | `src/evaluation/run_benchmark.py`, `ARMS` |
| Prompts antigos congelados por hash em teste | `tests/evaluation/test_benchmark_prompts.py` |

### A.3 Testes novos
- Toda construção documentada no prompt parseia; o que ele proíbe falha.
- O A2r difere do A2 só nos trechos previstos.
- Referência por rótulo: para trás, normalização do slug, em `message`; para
  frente rejeitada por decisão.
- Total: 362 testes passando.

### A.4 Achados de processo (não são resultado, mas afetam validade)
1. **Os comentários HTML dos prompts chegam ao modelo** (`load_prompt` não os
   remove). Os cabeçalhos de `xml_direct.md` e `dsl_grammar.md` diferem, então A1
   e A2 receberam textos meta diferentes. Sem evidência de efeito, mas é uma
   diferença entre braços não prevista no desenho.
2. A especificação (`dsl_documentation.txt`) contradizia a gramática. Ela nunca
   foi ao modelo (zero impacto nos números), mas era o que um leitor do
   repositório leria como referência.
3. O prompt do A2 tinha duas imprecisões (propriedades "em qualquer elemento";
   id "com dígitos") sem nenhuma ocorrência nas 477 saídas.

---

## Parte B — Resultados novos

### B.1 A2r contra A2 (mesmo modelo, só o prompt muda)
| métrica | A2 | A2r |
|---|---|---|
| Validade (parse = XSD) | 64,8% | **86,8%** |
| DF-F1 mediana por item | 0,1375 | 0,1804 |
| DF-F1 só nas válidas | 0,217 | 0,214 |
| TCR | 7,03 | 6,91 |

- 73% das falhas do A2 eram de referência (28 não resolvidas + 13 `#id` fora do
  lugar, de 56).
- O ganho é de forma, não de modelagem: a qualidade das válidas não muda.
- Pareado por item: 20 melhoram, 3 pioram (Wilcoxon p = 0,0045).

### B.2 A2r nos contrastes das hipóteses (exploratório, p sem Holm)
| contraste | p | leitura |
|---|---|---|
| A2r vs A1 | 0,40 | DSL **empata** com XML em fidelidade (H1 registrada: refutada com A2) |
| A4 vs A2r | 0,001 | modelo pequeno **pior** em fidelidade (H3 registrada: não refutada com A2) |

O efeito corta para os dois lados: fortalece a DSL e enfraquece a comparação de
fidelidade do modelo pequeno.

### B.3 Os 86,8% iguais de A2r e A4
Coincidência: falham em itens quase disjuntos (7 e 10 itens, 2 em comum) e por
motivos diferentes. A4 erra sempre nos mesmos itens, quase só por referência
`#id`; A2r erra espalhado, por deslizes variados. A parte "da linguagem" é a
referência e algumas irregularidades de sintaxe.

### B.4 Custo por requisição (preços de 12/10/2026)
| braço | US$ por 1M requisições |
|---|---|
| A1 (DeepSeek, XML) | 2.626 – 5.252 |
| A2r (DeepSeek, DSL) | 1.380 – 2.759 |
| A4 (7B + LoRA, DSL) | 337 – 506 (hipótese de preço) |

- DSL corta 47% no mesmo modelo.
- O ajuste fino economiza também na entrada (sem gramática no prompt).
- Ressalvas obrigatórias: nenhum provedor confirmado serve o adapter por token;
  cache de prefixo não modelado; tokenizador único; preços voláteis.
- **Script ainda não versionado** (`run_custo.py` pendente).

### B.5 Decisões tomadas hoje
1. O braço de fronteira com DSL da monografia passa a ser o A2r.
2. Tempo de inferência sai do argumento (hardware incomparável).
3. Eixo econômico = custo por requisição (tokens × preço de API).

---

## Parte C — Impacto por capítulo

Legenda: 🔴 afirmação central que os dados novos contradizem · 🟡 número ou
trecho a atualizar · 🟢 trecho que os dados novos reforçam · ❓ decisão sua.

### Resumo e Abstract (`resumo.tex`, `abstract.tex`)
- 🔴 "fornecer a gramática no prompt reduziu a confiabilidade: [...] 64,8% e
  56,6% [...] com significância estatística". Com o A2r, a gramática no prompt
  dá 86,8%.
- 🟡 "sete braços", "1.113 gerações".
- 🟡 Falta o eixo de custo em dinheiro, que vira o argumento central.
- Reescrever por último, depois dos capítulos.

**Feito em 2026-10-12:** os dois reescritos por inteiro, com o Abstract como
tradução frase a frase do Resumo (antes não era: faltavam 56,6% e a
fidelidade). Resumo com 404 palavras, Abstract com 400 (limite ABNT: 500).
Palavras-chave mantidas. Compilado: 0 erros, 0 indefinidas.

### Cap. 1 — Introdução (`tex/introducao.tex`)

**Feito em 2026-10-12:**
- I1 l. 18–20 reescritas: primeira versão pior, causa na referência, E-3 exploratória, o A4 com a mesma validade, fidelidade menor e 2–4× mais barato. Saiu o argumento "esses braços não constituem a configuração proposta";
- I2 l. 6 "contrariou, em parte";
- I3 Motivação: a condição é não exigir antecipação;
- I4 objetivo específico 5 inclui o custo por requisição;
- I5 Organização sem "de forma destacada [...] na íntegra";
- I6 sem "sete braços", mais o custo.

Compilado: 0 erros, 0 indefinidas. Estilo do autor preservado; só o que contradizia os Resultados foi tocado.
- 🔴 l. 18–20: "o que o registro prévio desmentiu [...] descrever a gramática no
  prompt [...] o observado é o oposto: 64,8% e 56,6%".
- 🟡 l. 8 e 31: o custo já é a motivação declarada ("o gargalo [...] é o custo").
  🟢 Base boa para o enquadramento custo-benefício.
- 🟡 l. 14: argumento de modelos pequenos (`belcak2025small`). Ajustar para
  "mesma validade, fidelidade menor, fração do custo".
- 🟡 l. 61: "sete braços".
- 🟡 Objetivos específicos (l. 41–50): incluir o eixo de custo, se não estiver.

### Cap. 2 — Fundamentação Teórica (`tex/fundamentacao-teorica.tex`)

**Feito em 2026-10-12:**
- F1 consequência da geração autorregressiva (esquerda para a direita, sem revisão), em §2.2.1;
- F2 custo financeiro por token de API, em §2.2.2;
- F3 corrigido "treinamento em estação local com 12 GB" para inferência local em 11 GB e treino em nuvem (erro anterior a hoje);
- F4 GRPO como trabalho futuro, alinhado com a Metodologia.

Não mexido: a seção de GED, que descreve uma métrica não adotada na v1. Compilado: 0 erros, 0 indefinidas.
- 🟢 l. 32–37 (verbosidade do XML) e l. 49–56 (custo de sequências longas):
  sustentam o novo enquadramento.
- 🟡 Possível parágrafo novo, curto: **geração autorregressiva da esquerda para a
  direita** (o modelo não volta para editar). É o conceito que explica o achado
  da referência. Talvez em §2.2.3 "Geração de Saídas Estruturadas" (l. 56).
- 🟡 l. 147 (TCR): conferir se fala de custo em dinheiro ou só de tokens.
- Pouca mudança no geral.

### Cap. 3 — Trabalhos Relacionados (`tex/trabalhos-relacionados.tex`)

**Feito em 2026-10-12:**
- T1 "ordens de grandeza menor" virou "2–4× menor";
- T2 garantia sintática "sempre que a DSL é aceita pela gramática";
- T3 referências inexistentes "detectadas e rejeitadas", não "impossíveis de expressar", restrito ao fluxo, porque em `message` o `#id` inexistente ainda gera referência solta, defeito em aberto;
- T4 o princípio de desenho contra as outras notações compactas;
- T5 a entrada domina o custo quando a gramática vai no prompt;
- T6 o modelo pequeno confirma a premissa em validade, não em fidelidade.

Compilado: 0 erros, 0 indefinidas.
- 🟢 l. 15: ProMoAI depende de modelo de fronteira, com custo por geração alto.
  Agora há número para isso.
- 🟢 l. 39: "o custo da saída" (assimetria entrada × saída). O achado de que no
  A2r a entrada domina o custo (gramática no prompt) complementa a seção.
- 🟡 l. 41 (modelos pequenos especializados): alinhar com "fidelidade menor".
- 🟡 l. 53 (decodificação restrita): o argumento "resolve validade, não custo"
  continua de pé.

### Cap. 4 — Metodologia (`tex/metodologia.tex`) — o capítulo mais sensível

**Feito em 2026-10-12 (opção a):** M1 (duas formas de referência, exceção ao
princípio "uma forma por conceito"), M3 (A2r na tabela de braços, quatro
prompts, 1.452 tokens), M4 (contrastes do A2r exploratórios, nas Hipóteses), M5
(fora do Holm), M6 (nova §"Custo por Requisição", `subsec:eixo-custo`, tempo
excluído), M7 (corpus só com `#id`). Compilado do zero: 0 erros, 0 referências
indefinidas, mesmos 4 overfull de antes. **Não aplicados, por decisão:** M2
(ressalva dos comentários HTML nos prompts) e M8 (64,8% na seção do GRPO).
**Pendente nos Resultados:** escrever a emenda E-3, que a Metodologia já cita
via `subsec:res-emenda`.

**Feito também (opção b, menos peso retórico, mesmos fatos):** B1 a seção de
pré-registro deixou a abertura do capítulo e virou §4.6.1 "Definição Prévia do
Protocolo", dentro de Protocolo de Avaliação (rótulo `sec:pre-registro`
mantido); B2 saiu "condiciona a leitura de todo o capítulo"; B3 saiu o negrito
de "integralmente congelado"; B4 saiu "prática incomum em TCC"; B5 a frase do
A2r nas Hipóteses ficou seca; B6 tabela "Hipóteses pré-registradas" →
"Hipóteses". Compilado: 0 erros, 0 indefinidas. Peso retórico restante fora da
Metodologia: `resultados.tex:128` e `introducao.tex:18–20`.
- ❓🔴 **l. 23–30, seção "Pré-registro do Protocolo Experimental".** É o ponto de
  decisão de todo o trabalho. A seção promete que toda alteração posterior é
  "emenda datada, com indicação de se ocorreu antes ou depois da observação dos
  resultados". O A2r foi desenhado **depois**. Opções:
  - (a) A2 vira "primeira versão do prompt" e o A2r a revisão, narrada como
    emenda pós-observação (E-3), com data. Mantém a coerência da seção.
  - (b) Reduzir o peso do pré-registro no texto todo. Mudança grande, e exigiria
    reescrever também os Resultados.
- 🟡 l. 113–135 (A BPMN-DSL): o exemplo usa `#fetch`. Apresentar as duas formas
  de referência; o exemplo pode passar a `#"Fetch data"`.
- 🟡 l. 140–149 (JSON para DSL): o corpus continua só com `#id`. Dizer isso
  explicitamente (e que o modelo ajustado só viu essa forma).
- 🟡 l. 217–226 (Eixo 4, Compressão): acrescentar o **custo por requisição** como
  métrica, com a fórmula (tokens de entrada × preço + tokens de saída × preço) e
  as fontes de preço com data.
- ❓🟡 l. 235–268 (Desenho dos braços): onde o A2r entra. Como braço principal
  no lugar do A2 ou ao lado dele.
- ❓🔴 l. 272–301 (Hipóteses H1, H1g, H3): estão definidas sobre o **A2**. Não se
  troca o braço de uma hipótese registrada depois de ver o resultado. Caminho
  compatível com (a): H1/H3 continuam reportadas com A2 e os mesmos contrastes
  com A2r entram como exploratórios.
- 🟡 l. 307–318 (Parâmetros e estatística): contrastes exploratórios sem Holm.
- 🟡 Ameaças à validade: comentários HTML dos prompts enviados ao modelo.
- Tempo: garantir que nada promete medir latência.

### Cap. 5 — Resultados (`tex/resultados.tex`) — onde fica o grosso do trabalho

**Feito em 2026-10-12:**
- R1 emenda E-3 escrita (com `tab:res-e3`), "três emendas";
- R2 antecipação do desfecho reescrita; saiu "o pré-registro existe precisamente para...";
- R3 parágrafo da "novidade" reescrito (a causa é a referência);
- R4 Síntese: cadeia, afirmação final e achados exploratórios reescritos, tabela renomeada para "hipóteses registradas";
- R5 linha do A2r no panorama e "quarta leitura" reescrita;
- R6 `tab:res-testes-a2r` (A2r vs A1 p = 0,40; A4 vs A2r p = 0,001);
- R7 duas linhas novas na tabela condicional e as "duas intervenções";
- R8 o A4 iguala o A2r, mais a subseção da coincidência dos 86,8%;
- R9 linha do A2r na TCR e `tab:res-custo` com cenário de cache simétrico e ressalvas;
- R10 diagnóstico: testado no modelo de fronteira, não no ajustado;
- R11 figuras de validade e de custo (eixo x em US$);
- R12 nota do A2r na abertura dos exploratórios.

Compilado do zero: 0 erros, 0 indefinidas, mesmos 4 overfull; 97 páginas.
- 🔴 l. 124–128: "H1, H1g e H2 foram refutadas"; "o achado de maior magnitude
  [...] o modelo de 7B". Com o A2r, o maior achado passa a ser a referência por
  rótulo, e o 7B deixa de ser único em 86,8%.
- 🟡 l. 130–165 (Tabela descritiva por braço + figura de validade): incluir o A2r.
  A progressão da l. 163 ("0% sem gramática, 58,5% com gramática, 86,8% com a
  notação nos pesos") ganha um degrau: 86,8% com gramática e referência por
  rótulo.
- 🟡 l. 167–198 (Testes das hipóteses): manter como estão (registrados) e
  acrescentar os contrastes com A2r como exploratórios. **Reportar o A4 vs A2r
  (p = 0,001) sem atenuar.**
- 🟢 l. 200–230 (Mecanismo: validade e não qualidade): o A2r confirma a tese da
  seção diretamente. DF-F1 condicional igual (0,217 × 0,214): o problema era
  forma, não qualidade.
- 🟡 l. 231–265 (Modelo especializado + Fig. custo): a figura `figuras/custo.tex`
  ganha o ponto do A2r (≈141 tokens, 86,8%), que fica **em cima** do A4 em
  validade e à esquerda em tokens. Reescrever a l. 262–264 ("posição" no plano
  custo-validade) com custo em dinheiro em vez de só tokens de saída.
- 🟡 l. 266–277 (Verificações de validade): acrescentar os comentários HTML.
- 🟡 l. 279–323 (Emendas): se a opção (a), a E-3 entra aqui.
- 🔴🟡 l. 325–354 (Eixo econômico): hoje é só TCR e tokens de saída. Vira o
  centro do capítulo, com a tabela de custo por requisição (B.4), a observação
  de que no A2r a entrada domina e as ressalvas de preço. A frase "a pergunta
  que resta, formalizada em H3" muda de resposta.
- 🟢 l. 626–636 (Diagnóstico: a notação exige antecipação): já diagnostica o
  problema para os modelos ajustados e propõe a referência por rótulo. O A2r é a
  **confirmação experimental** dessa previsão: entra logo depois, como
  continuação natural. É o melhor gancho do texto.
- 🟡 l. 638–662 (Síntese, "cadeia argumentativa"): reescrever com a cadeia nova.
- 🟡 Nova subseção curta: os 86,8% iguais são coincidência (B.3).

### Cap. 6 — Conclusão (`tex/conclusao.tex`)

**Feito em 2026-10-12:**
- C1 a resposta sobre confiabilidade: primeira versão pior, causa na referência, A2r e A4 em 86,8%;
- C2 explicação: antecipação, não novidade; o ajuste fino vira escolha de custo;
- C3 "Evidência empírica" requalificada, sem "prática incomum";
- C4 contribuição nova, o princípio de desenho de notações para geração autorregressiva;
- C5 "Viabilidade econômica" em custo por requisição, com a troca explícita;
- C6 duas limitações novas: A2r exploratório em um modelo só; custo do A4 estimado e tempo não comparado;
- C7 trabalho futuro: referência por rótulo no modelo especializado, rótulo para frente e replicação no GLM;
- C8 e C9 frases ajustadas.

Conferido: o A2r fica abaixo do teto humano nos 24 itens (0,119 < 0,1449), então "apenas o XML direto ultrapassa" continua verdadeiro. Compilado: 0 erros, 0 indefinidas.
- 🔴 l. 6: "fornecida por prompt, ela piora o resultado".
- 🔴 l. 8: "verbosidade não constitui dificuldade [...] novidade, sim [...] o
  benefício [...] não se realiza por instrução, e sim por especialização [...]
  ajuste fino [...] condição necessária". O A2r contradiz diretamente: por
  instrução, com a referência adequada, chega a 86,8%. A tese nova: **o problema
  era antecipação, não novidade**; o ajuste fino vale pelo **custo** (dispensa a
  gramática no prompt e roda num modelo pequeno), não por ser o único caminho
  para a validade.
- 🟡 l. 15: "três hipóteses foram refutadas" continua verdade para os
  registrados, mas precisa do contraponto do A2r.
- 🟡 l. 17 (viabilidade econômica): trocar tokens por custo em dinheiro e citar
  as ressalvas.
- 🟡 l. 21–34 (Limitações): acrescentar o preço do A4 como hipótese, a ausência
  de provedor confirmado, cache não modelado, tempo excluído e o A2r pós-hoc.
- 🟡 l. 41 (Trabalhos futuros, "Convenção de referência por rótulo"): metade foi
  feita hoje (modelo de fronteira). Reescrever: o que falta é **retreinar o A4
  com corpus que use rótulo**, já que 15 das 21 falhas dele são de referência.
  O custo citado (2,31% em tokens, sobre o corpus) pode ser comparado com o
  medido no A2r (1,7%, sobre as saídas).
- 🟡 Trabalho futuro novo: replicar o A2r no GLM (A2g).

### Elementos de apoio
- `figuras/custo.tex` + `figuras/dados/custo_*.csv`: acrescentar o A2r e talvez
  trocar o eixo x de tokens para US$.
- `figuras/validade.tex`: acrescentar o A2r.
- `src/evaluation/export_figuras.py`: `BRACOS` não inclui `X-a2r`.
- `lista-de-abreviaturas-e-siglas.tex`: conferir se A2r ou custo pedem sigla.

---

## Parte D — Pendências antes de escrever

| # | pendência | tipo |
|---|---|---|
| 1 | Decidir a opção do pré-registro (a ou b) | ❓ decisão sua; condiciona Metodologia e Resultados |
| 2 | Versionar o cálculo de custo (`run_custo.py`), com cenário de cache | código |
| 3 | Atualizar `export_figuras.py` e as figuras com o A2r | código |
| 4 | Replicar o A2r no GLM (159 chamadas) | ❓ opcional; responde se o efeito é da notação ou do DeepSeek |
| 5 | Retreinar o A4 com referência por rótulo | ❓ opcional; trabalho futuro ou execução até 30/11 |
| 6 | Commitar o trabalho de hoje (nada commitado) | git |
