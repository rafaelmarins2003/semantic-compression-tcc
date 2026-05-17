# Fundamentação Teórica - Entrega da disciplina

Projeto LaTeX autocontido (template UniforTeX2 / abnTeX2) com a fundamentação teórica do TCC.

## Estrutura

```
referencial_teorico/
├── main.tex                                    # entrada do compilador
├── lib/                                        # macros do template Unifor
├── elementos-pre-textuais/
│   └── lista-de-abreviaturas-e-siglas.tex      # siglas carregadas pelo template
├── elementos-textuais/
│   └── fundamentacao-teorica.tex              # CAPÍTULO PRINCIPAL
└── elementos-pos-textuais/
    ├── glossario.tex                           # glossário carregado pelo template
    └── referencias.bib                         # bibliografia
```

## Como compilar

### Overleaf

No Overleaf, configure o documento principal como `main.tex`.

Se o log mostrar `"<*> preambulo.tex"` ou erro em `lib/preambulo.tex` com `no legal \end found`, o Overleaf está compilando o arquivo errado. Abra o menu do projeto e ajuste **Main document** para `main.tex`.

### Opção 1 - latexmk (recomendado)
```bash
cd article/cadeira_tcc/referencial_teorico
latexmk -pdf main
```

### Opção 2 - pdflatex + bibtex manual
```bash
cd article/cadeira_tcc/referencial_teorico
pdflatex main
bibtex   main
pdflatex main
pdflatex main
```

O PDF gerado é `main.pdf`. Renomeie para `Rafael_Marins_Florenzano_Fundamentação.pdf` antes de submeter.

### Dependências

- Distribuição LaTeX (TeX Live ou MikTeX) com pacotes ABNT: `abntex2`, `abntex2cite`
- No Fedora/Nobara: `sudo dnf install texlive-scheme-full` (pesadão; alternativa mínima: `texlive-abntex2` + dependências)

## Conteúdo

O capítulo está estruturado em 6 seções principais + síntese:

1. **Modelagem de Processos de Negócio e a Notação BPMN 2.0**: define o domínio empírico
2. **Modelos de Linguagem de Grande Escala**: Transformer, tokenização, geração estruturada
3. **Linguagens de Domínio Específico e Compressão Semântica**: enquadramento teórico do trabalho
4. **Adaptação de Modelos de Linguagem a Tarefas Específicas**: SFT, LoRA/QLoRA, GRPO
5. **Extração de Processos a partir de Texto Natural**: datasets e desafios
6. **Avaliação de Geração de Artefatos Estruturados**: XSD, F1, GED, TCR

## ⚠️ Verificações antes da submissão

### 1. Substituições obrigatórias
- [ ] `João José Vasco Peixoto Furtado` em `main.tex` → nome real
- [ ] Ano de defesa (`\data{2026}`): confirmar se está correto
- [ ] Título do TCC: confirmar redação com o(a) orientador(a)

### 2. Bibliografia (`elementos-pos-textuais/referencias.bib`)

As entradas bibliográficas foram verificadas em fontes primárias ou catálogos editoriais em 17/05/2026:
Springer, ACL Anthology, NeurIPS Proceedings, OpenReview, arXiv, Zenodo, OMG e InformIT/Pearson.
Antes da submissão, ainda vale conferir visualmente no PDF se o `abntex2cite` renderizou todos os campos
em formato adequado.

- [x] Autoria do PMo Dataset corrigida para Alexis Brissard, Frédéric Cuppens e Amal Zouaq
- [x] Autoria do dataset de Mangler corrigida para Juergen Mangler e Nataliia Klievtsova
- [x] Ano e veículo do PET corrigidos para publicação Springer/LNBIP de 2023
- [x] Referência de Graph Edit Distance corrigida para Gao et al. (2010)
- [ ] Confirmar com o(a) orientador(a) se a especificação BPMN deve permanecer na versão 2.0 ou migrar para 2.0.2

### 3. Adequação ao Turnitin

O texto foi redigido de forma própria, sem cópia de fontes externas. Mesmo assim:

- [ ] Rodar verificação de similaridade interna (ferramentas como `git diff` contra qualquer texto-base utilizado anteriormente)
- [ ] Para citações diretas longas (acima de 3 linhas), usar o ambiente `\begin{citacao}...\end{citacao}` do `abntex2` (recuo de 4 cm)
- [ ] Para citações diretas curtas, usar aspas duplas + `\cite[p.~x]{}`
- [ ] As citações indiretas usadas aqui parafraseiam as ideias dos autores; sempre acompanhadas de `\cite{}` ou `\citeonline{}`

### 4. Coerência com o projeto

O conteúdo foi construído a partir do que está documentado em:
- `CLAUDE.md` (stack, decisões, contexto de pesquisa)
- `fontes.txt` (datasets selecionados)

Caso decisões do projeto mudem (ex: substituição de Qwen2.5-Coder por outro modelo base, alteração nos pesos da recompensa GRPO, descarte de algum dataset), **atualizar as seções correspondentes** antes da defesa final. A entrega de disciplina não precisa refletir essas mudanças.

### 5. Possíveis adições futuras (não exigidas nesta entrega)

- Figura ilustrando o pipeline do projeto (texto → DSL → XML → validação)
- Tabela comparativa dos datasets utilizados (PMo, PET, Mangler, Handbook, MaD)
- Trecho de exemplo de DSL × XML BPMN equivalente, evidenciando a compressão
- Diagrama da arquitetura LoRA (caso o orientador peça)

Os ganchos para inclusão de figuras já existem no template (`\begin{figure}` + `\UNIFORfig{}` + `\Caption{}` + `\Fonte{}`).

## Integração com o TCC final

Quando for montar a versão completa do TCC, este conteúdo deve ser movido para
`article/Atualização Template TCC Unifor 2022.2/elementos-textuais/fundamentacao-teorica.tex`
(substituindo o conteúdo de exemplo).

As entradas bibliográficas devem ser fundidas com
`article/Atualização Template TCC Unifor 2022.2/elementos-pos-textuais/referencias.bib`.

Não é necessário copiar `lib/` nem `main.tex`; o projeto completo do TCC já tem os seus.
