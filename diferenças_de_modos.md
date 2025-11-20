# Diferenças entre os modos de tradução

Este documento resume como cada modo opera internamente e quais arquivos do projeto coordenam o fluxo.

## Arquitetura verificada

- `scripts/mvp_cli.py`: seleciona o modo via `--mode`, instancia os serviços adequados e injeta telemetria.
- `src/services/translation_service.py`: implementa os modos `node` e `window` usando `TranslationGateway` e o backend Hugging Face.
- `src/segmentation.py`: fornece `build_windows` e `split_window_translation`, usados apenas no modo `window`.
- `src/services/doc_level_service.py`: lineariza o documento, chama o backend escolhido (HF ou Google) e reparte o resultado para o modo `doc`.
- `src/services/doc_syntactic_service.py`: estende o serviço anterior adicionando heurísticas/sintaxe para redistribuir as traduções nos nós originais (modo `doc-sintatico`).
- `src/telemetry/` (opcional): observa e registra eventos do fluxo, reutilizado por todos os modos quando `--observe` é passado.

## Modo `node`
1. Cada nó textual é tratado isoladamente em `TranslationService.translate_node`.
2. O texto do nó é enviado diretamente ao backend (`HuggingFaceBackend` normalmente, definido em `src/backends/hf_backend.py`).
3. O resultado é salvo no banco sem qualquer junção ou segmentação complementar.
4. Vantagens: consumo baixo de memória/tokens e traduções rápidas.
5. Limitações: perda de contexto entre nós gera traduções mais literais e inconsistentes.

## Modo `window`
1. `TranslationService.translate_nodes_windowed` agrupa nós contíguos com `build_windows` (`src/segmentation.py`), criando blocos que respeitam um orçamento de caracteres.
2. Cada janela concatenada recebe marcadores `<<<NODE:id>>>` para permitir dividir o retorno depois.
3. O backend traduz a janela inteira; `split_window_translation` reparte a resposta de volta aos nós originais.
4. Fornece contexto local sem precisar traduzir o documento inteiro, equilibrando qualidade e custo.

## Modo `doc`
1. `DocLevelTranslationService.linearize` monta um único texto com marcadores `<N#>...</N#>` representando a ordem dos nós (único ponto que respeita `short_node_merge_chars`).
2. Opcionalmente o serviço consulta RAG (`src/rag/retriever.py`) para construir um contexto adicional se habilitado.
3. O backend recebe o documento inteiro, e `parse_translated` separa a saída usando os marcadores.
4. Quando um marcador representa um grupo (IDs unidos), o retorno é quebrado por linhas; sem heurística extra, qualquer desalinhamento resulta em trechos vazios.
5. Este modo busca máxima coerência global, mas pode estourar limites de token em modelos seq2seq.

## Modo `doc-sintatico`
1. Reutiliza todas as etapas do modo `doc` para linearizar, consultar RAG e traduzir (mesmo texto de saída).
2. Após a tradução, `DocSyntacticTranslationService._split_group_text` tenta manter sentido ao redistribuir grupos:
   - Prioriza quebras de linha já presentes.
   - Se houver spaCy instalado para o idioma alvo, usa `doc.sents` para dividir por sentenças.
   - Caso contrário, aplica regex de pontuação ou uma divisão proporcional por tokens.
3. Cada subtrecho é associado ao nó correspondente, evitando que apenas o primeiro receba todo o texto.
4. O resultado final tem tom idêntico ao modo `doc`; a diferença é a forma como o texto é particionado quando vários IDs foram fundidos antes da tradução.

## Observações gerais
- Todos os modos dependem do pipeline de ingestão e persistência (`src/dom_indexer.py`, `src/persistence/`), que não mudam entre estratégias.
- A decisão do backend (`translation.backend`) vale para todos os modos; com Google LLM recomenda-se o modo `doc`/`doc-sintatico` devido ao prompt estruturado.
- O parâmetro `short_node_merge_chars` influencia somente os modos `doc` e `doc-sintatico`, definindo quando nós curtos são agrupados antes da tradução.
