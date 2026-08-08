# TODO

Estado atual:

- XML BPMN a partir do DSL já existe e passa em validação XSD.
- Conversor determinístico JSON -> XML direto foi criado em
  `src/data/manipulation/deterministic/json_to_xml.py`.
- Layout/BPMNDI determinístico foi criado como pós-processador comum em
  `src/transpiler/layout.py`.
- Testes manuais validaram JSON -> XML direto vs JSON -> DSL -> XML com:
  XSD válido, BPMNDI presente, equivalência topológica e CLI funcionando.

Próximo passo:

1. Criar/ajustar o harness de avaliação para armazenar no banco os resultados do
   baseline JSON -> XML direto e comparar contra JSON -> DSL -> XML.
2. Rodar essa avaliação no conjunto completo e registrar métricas para o artigo:
   XSD, equivalência topológica/direct-follows e diferenças residuais.
3. Inspecionar visualmente alguns BPMNs com layout para garantir que o BPMNDI é
   suficiente para leitura humana, sem usar qualidade visual como métrica principal.
4. Depois da avaliação estar fechada, seguir para finetuning/SFT.

PS: sempre que terminar o dia, deixar o TODO atualizado para não perder o ponto
de retomada.
