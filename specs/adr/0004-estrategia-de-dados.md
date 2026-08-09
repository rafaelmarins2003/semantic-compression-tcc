# ADR 0004 — Estratégia de dados: medir antes de coletar

| Campo | Valor |
|---|---|
| Status | **Aceita** |
| Data | 2026-08-09 |
| Decide | se coletar mais dados antes do harness de avaliação |
| Afeta | ordem das fases; prioridade 5 (SFT) e 7 (publicação) |

## Contexto

Antes de iniciar a [spec 004](../004-camada-de-dados/spec.md), levantou-se a
questão de dar um passo atrás e buscar mais fontes de dados — mais scraping —
para treinar com um corpus maior.

Medição da concentração do conjunto de treino (2026-08-09):

| Fonte | n | % do treino |
|---|---|---|
| gitlab_handbook | 900 | **95,3%** |
| pet | 44 | 4,7% |
| **total** | **944** | |

O CLAUDE.md registrava 71%; o número estava desatualizado e foi corrigido.

## Decisão

**Seguir para a Fase 4 sem coletar dados novos.** A decisão sobre volume e
diversidade fica para depois da Fase 5, apoiada nos resultados do harness.

### Razões

1. **Cinco dos seis braços não usam dado de treino.** A1/A2 (`deepseek-v4-pro`,
   independente do corpus), A1g/A2g (`glm-5.2`, o gerador) e A3 (Qwen base) são
   todos prompted. A alegação central da tese — DSL comprimida bate XML direto —
   é medida por A2 vs A1 com zero amostra de treino. Só A4 (SFT) depende do
   corpus, e A4 entra na **Fase 7** do TODO (SFT e publicação), correspondente à
   *prioridade 5* do CLAUDE.md — as duas numerações não coincidem.

   _(Atualizado em 2026-08-09: o desenho passou de quatro para seis braços na
   mesma leva de mudanças que criou este ADR. A1g/A2g usam o próprio gerador do
   corpus, o que dá a leitura de destilação; o baseline independente continua
   sendo A1/A2. Ver spec 003 §4.)_
2. **O harness é o instrumento que responde a pergunta.** Coletar antes é
   otimizar uma grandeza que ainda não se consegue avaliar. Com A3 medido contra
   o gold, a distância até o alvo diz quanto o SFT precisa entregar.
3. **O gargalo provável não é volume.** 772 pares é razoável para LoRA numa
   tarefa de formato — extração estruturada sob gramática fixa, não conhecimento
   novo. _(Julgamento por analogia, não medição neste projeto — ver Incerteza.)_

## O risco real é concentração, não volume

Com 95,3% de uma única empresa, a ameaça é generalização: o modelo aprende o
estilo de escrita da GitLab e é avaliado contra o PMo, outro domínio e outro
registro. **Mais scraping de handbook pioraria isso**, aumentando volume e viés
ao mesmo tempo. Qualquer coleta futura tem de ser julgada por diversidade de
fonte, não por quantidade.

Isso precisa constar da monografia como ameaça à validade externa em seção
própria, não como nota de rodapé.

## Fontes candidatas, se a evidência pedir

Em ordem de retorno por esforço:

1. **Geração reversa a partir de coleções públicas de modelos BPMN** (BPM
   Academic Initiative, exemplos Camunda/bpmn.io): modelo → texto via LLM. O
   gold vem de graça e modelos são mais abundantes que pares. **Ressalva**: texto
   gerado por LLM não tem a distribuição de texto humano — complemento, nunca
   maioria.
2. **Outros handbooks abertos** (Basecamp, HashiCorp, Automattic, Buffer,
   Oyster): mesmo pipeline já validado, estilos diferentes. Menor atrito técnico.
3. **Friedrich et al. (2011)** — já citado no `.bib` e na fundamentação; tem
   corpus de pares texto-modelo feito por humanos. Pequeno mas diretamente na
   tarefa. Verificar disponibilidade antes de qualquer scraping novo.
4. **Procedimentos de setor público e universidades**: SOPs altamente
   procedurais, públicos, e em domínio bem distante da GitLab.
5. **MaD (Li et al. 2023)**, 30k pares — já classificado como baixa
   variabilidade. Serve como enchimento de volume, que é o que não falta.

**Restrições para qualquer fonte nova**: nada que se sobreponha a PMo ou Zenodo,
sob pena de contaminar o holdout; e cada fonte entra com tag/`prompt_version`
própria, para o efeito dela ser medível isoladamente.

## Incerteza registrada

A afirmação de que 772 pares bastam é analogia com tarefas semelhantes, não
medição deste projeto. Para reduzi-la sem coletar nada: treinar com metade do
corpus e comparar com o corpus inteiro — a inclinação entre os dois pontos
indica se mais dados ainda rendem. Custa uma rodada extra de treino.

## Consequências

- A ordem das fases não muda: 4 → 5 → 6 → 7.
- Se A3 ficar muito abaixo do alvo, este ADR é revisitado com número em mãos.
- A limitação de concentração entra na monografia independentemente do desfecho.
