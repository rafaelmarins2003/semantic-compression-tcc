# ADR 0003 — Temperatura 0 não garante determinismo

| Campo | Valor |
|---|---|
| Status | **Aceita** |
| Data | 2026-08-08 |
| Afeta | [spec 003](../003-eval-harness/spec.md) §6.2 e §6.3 |
| Origem | duplicatas acidentais no piloto da spec 004 |

## Contexto

O piloto de seleção de modelo rodou duas vezes em paralelo por engano
operacional. O acidente produziu medições repetidas dos mesmos pares
(configuração, amostra), todas com `temperature=0.0`. Elas **discordam**:

| Config | Divergem em XSD | Divergem em nº de nós | Pares repetidos |
|---|---|---|---|
| `deepseek-v4-flash:0731-cloud` | 7 | 33 | 50 |
| `glm-5.2:cloud` | 0 | 7 | 11 |

Dois terços das repetições produzem estrutura diferente, e em um dos modelos a
própria **validade XSD** muda entre execuções idênticas.

Causa provável: modelos servidos em nuvem não garantem reprodutibilidade
bit-a-bit — batching dinâmico, roteamento de MoE e kernels não determinísticos
alteram o resultado independentemente da temperatura.

## Decisão

**Tratar `temperature=0` como redutor de variância, não como garantia de
determinismo.** Nenhum protocolo do projeto pode assumir que reexecutar produz o
mesmo resultado.

Consequências para a spec 003:

1. **§6.2 — `k=1` deixa de ser adequado como execução principal.** Medição de
   tiro único carrega variância não medida; comparação pareada entre braços com
   n=53 fica exposta a ruído maior que o efeito esperado.
2. **§6.3 — a análise precisa separar variância entre braços de variância dentro
   do braço.** Com k>1, a unidade de análise passa a ser a média por item.
3. **Reprodutibilidade da tese**: os números não são reproduzíveis por
   reexecução, apenas por reuso das saídas gravadas. O banco passa a ser o
   registro autoritativo do resultado, e isso precisa ser declarado no texto.

O valor de `k` e o teste estatístico correspondente ficam **em aberto** e devem
ser fixados antes do congelamento da spec 003.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter k=1 e ignorar | Falsifica a premissa explícita de §6.2; a banca pode reexecutar e obter outro número |
| Exigir determinismo do provedor | Fora de controle: nenhum provedor de nuvem oferece essa garantia |
| Rodar tudo local para determinismo | Inviável no hardware disponível para modelos desse porte |

## Observação de método

Este achado veio de um **erro operacional**, não de um experimento planejado. A
medição de variância só existiu porque o engano duplicou execuções. Vale
considerar medir variância de propósito — é barato e teria sido descoberto de
forma controlada em vez de acidental.
