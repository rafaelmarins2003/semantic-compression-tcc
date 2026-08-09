# ADR 0001 — Idioma dos artefatos gerados

| Campo | Valor |
|---|---|
| Status | **Aceita** |
| Data | 2026-08-08 |
| Afeta | specs 003 (harness), 004 (camada de dados), prioridades 5 (SFT) e 7 (publicação) |

## Contexto

Todos os textos-fonte da base são em inglês (GitLab Handbook, PET, PMo, Zenodo),
e o gold do PMo Benchmark também (`"Record order in system"`). Apesar disso, as
1021 amostras geradas têm rótulos em **português** em todas as quatro fontes:

```
gitlab_handbook -> 'Utilização e Manutenção do Handbook', 'Colaborador'
pet             -> 'Revisão de Dispensas', 'Enviar Dispensa'
pmo             -> 'Recrutamento e Onboarding', 'Departamento'
zenodo          -> 'Gestão de Candidaturas de Emprego', 'Candidato'
```

Causa: os prompts em `configs/prompts/` estão escritos em português
(`<role>Arquiteto BPMN 2.0 Senior</role>`) e **não contêm diretiva de idioma**.
O modelo espelhou a língua da instrução em vez da língua da entrada.

Consequência se mantido: a identidade de nó em `src.evaluation.topology` é o
rótulo normalizado, então comparar geração em PT contra gold em EN produz
F1 ≈ 0 **por construção** — o número não mediria qualidade alguma. Isso quebra
o eixo principal da spec 003 e, por tabela, o SFT (o modelo aprenderia
texto EN → DSL PT) e a publicação do dataset.

## Decisão

**Os artefatos gerados — JSON canônico, DSL e BPMN — usam inglês nos rótulos.**

O texto da monografia permanece em português. A língua dos artefatos acompanha a
língua dos dados de origem e do gold, não a do documento acadêmico.

Operacionalmente:

1. Os prompts passam a conter diretiva explícita de idioma de saída.
2. Os dois estágios de LLM são reexecutados sobre as 1021 amostras
   (`preprocessing_generations` e `json_bpmn_generations`), com novas
   `prompt_version`.
3. As etapas determinísticas (`json_to_dsl`, `dsl_to_xml`, `layout`) são apenas
   reprocessadas — não mudam.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter PT + matching por embedding/LLM-juiz | Injeta componente não determinístico na métrica primária, exatamente o que a spec 003 §3.4 isolou como frágil e manteve fora das conclusões |
| Manter PT + métrica só estrutural | Perde poder discriminativo: dois processos de mesma forma e conteúdo diferente pontuam igual; enfraquece a alegação de fidelidade semântica |
| Regerar só o holdout (77 itens) | Barato e resolve A1–A3, mas A4 (modelo SFT treinado em PT) continua quebrado contra gold em inglês |

## Consequências

**Positivas** — métrica primária segue determinística e verificável por código;
dataset publicável fica coerente com as fontes; A4 passa a ser comparável.

**Negativas** — custo de reexecutar 2042 chamadas de LLM; os números atuais do
eixo 2 (1015/1021) e o TCR medido (5,08) precisam ser **recalculados** sobre a
base regenerada antes de irem para a tese. Nada indica que mudem de forma
relevante, mas são medições sobre dados que deixarão de existir.

**Registro** — as versões antigas permanecem no banco sob a `prompt_version`
anterior; a regeneração não apaga histórico.
