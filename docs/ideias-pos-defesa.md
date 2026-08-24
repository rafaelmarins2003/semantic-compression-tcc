# Ideias pós-defesa

Ideias de **produto e artefato** que não são trabalho de TCC e não entram na
monografia, mas que valem depois de 30/11. Não confundir com a seção de
Trabalhos Futuros da conclusão, que reúne **perguntas de pesquisa** — estas aqui
são de engenharia e disseminação.

Regra do arquivo: cada ideia registra o que é, por que ficou de fora, o que já
existe pronto a favor dela, e o que faltaria. Ideia sem "o que faltaria" é
desejo, não plano.

---

## Transpilador BPMN público, portável (C++/WASM)

**Origem**: conversa de 2026-08-23. A pergunta inicial era reescrever o
transpilador em C++ "para ficar mais rápido".

**Velocidade não é o argumento, e isso está medido.** O pipeline determinístico
custa **27,3 ms por documento** (21,1 ms de parse+XML com lark, 6,2 ms de
leiaute); o corpus inteiro de 1.021 documentos sai em 28 s. A geração mediana do
braço A4 leva **15,4 s**. O transpilador é **0,18% do custo de ponta a ponta** —
torná-lo instantâneo economizaria menos de dois décimos de por cento. Se algum
dia a velocidade importar, a primeira alavanca está dentro do Python (algoritmo
do parser do lark, cache da gramática compilada), não fora dele.

**O argumento real é portabilidade e embutibilidade**: binário único, sem
runtime Python, e sobretudo **WASM**. Uma página que aceita a DSL, mostra o BPMN
e entrega o arquivo, sem backend algum, é capacidade que a implementação atual
não oferece.

**Ordem de valor público** (do mais para o menos útil a terceiros):

1. **Leiaute determinístico (BPMNDI) isolado.** É o artefato mais afiado. Um
   BPMN sem a seção de *diagram interchange* é válido perante o esquema e abre
   como tela em branco na maioria dos modeladores — a monografia já registra
   isso. Muita ferramenta emite BPMN XML; poucas emitem BPMN que **abre**.
   Pacote pequeno, escopo nítido, dor real.
2. **A DSL e sua gramática.** O espaço de bibliotecas BPMN não é vazio (bpmn-js,
   API do Camunda, pm4py, SpiffWorkflow), mas o nicho "DSL textual compacta com
   gramática EBNF formal e expansão determinística verificável" é fino.
3. **A implementação em C++/WASM.** Meio, não fim.

**A favor, já pronto**: 1.021 documentos com saída conhecida e equivalência
topológica verificável (`src.evaluation.topology`), mais validação XSD 1021/1021.
Isso é suíte de regressão de ouro — torna a reescrita segura e vira argumento de
venda ("validado contra 1.021 modelos de processo reais").

**O que faltaria**: substituir lark por um gerador de parser em C++ e lxml por
libxml2 ou Xerces para a validação XSD; reconquistar a garantia de esquema; e
uma camada de testes diferenciais contra a implementação Python sobre os 1.021.

**Por que não agora**: o transpilador carrega a garantia mais forte da tese
(XSD 1021/1021, DF-F1 0,9999). Reescrever a três meses da entrega significa
reconquistá-la do zero, e divergência entre duas implementações é classe de bug
nova. Nenhuma alegação da monografia melhora com a troca.

**Por que não vai para a monografia**: a seção de Trabalhos Futuros da conclusão
tem seis itens, todos perguntas de pesquisa. Um item de engenharia leria como
desejo pessoal e enfraqueceria a lista. A disseminação do artefato já está
prometida na seção de Reprodutibilidade, sem comprometer linguagem de
implementação.
