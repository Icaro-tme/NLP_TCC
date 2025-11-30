## Diferenças entre modos de tradução (node, window, doc, doc-sintatico)

Este documento descreve com precisão as características atuais de cada modo após a atualização que introduziu dual-pass (baseline vs adapted) também para `node` e `window`, além de melhorias de segmentação sintática para chunking seguro em entradas longas.

### Visão Geral dos Modos

- **node**: Tradução nó-a-nó isolada. Menos contexto, maior velocidade, mas perda de coesão terminológica em documentos jurídicos extensos.
- **window**: Agrupa nós vizinhos em janelas (~800 chars padrão) para fornecer contexto local antes de repartir a tradução. Melhora consistência em sequências de parágrafos relacionados sem custo total de doc-level.
- **doc**: Lineariza todo o documento usando marcadores `<N#>...</N#>` conservando ordem e limites de bloco. A tradução ocorre em uma única chamada ao backend e é mapeada de volta. Melhor coerência global.
- **doc-sintatico**: Extensão do `doc` com heurísticas sintáticas (spaCy + divisões por pontuação / proporção) para distribuir grupos curtos que foram previamente unidos na fase de linearização, evitando acúmulo artificial de texto.

### Dual-Pass (Baseline vs Adapted)

Dual-pass existe para permitir comparação objetiva entre:
1. **Baseline**: Tradução sem qualquer contexto externo (RAG desativado, nenhum snippet de glossário/corpus usado).
2. **Adapted**: Tradução com contexto recuperado via RAG (glossário + corpus) que influencia forçosamente (no caso HF) por termos-alvo (forced decoding) ou orienta LLM (Google) via prompt.

### Construção de Contexto (RAG)

Em todos os modos dual-pass agora:
- Recuperação usa `Retriever` (SentenceTransformer + índice persistido) sobre glossário e corpus.
- Se índice não existe, é construído antes da primeira recuperação (lazy build).
- Filtro de relevância considera idiomas fonte/destino (glossário) e língua do snippet (corpus).
- Limite de caracteres concatenados controlado por `rag.max_context_chars` (padrão 5000).
- Formato do contexto: blocos com cabeçalho `[Fonte: <id> | score=... | ...]` seguidos do conteúdo. Esse formato permite extração posterior de pares glossário para heurísticas.

### Hugging Face Backend (HF) vs Google LLM

- **HF (seq2seq)**: Contexto adaptado gera lista de termos alvo (até 8) presentes no texto fonte — aplicados via `force_words_ids` para guiar a decodificação sem superconstranger. Baseline não usa força de termos.
- **Google**: Contexto concatenado ao prompt (doc-level). Para node/window não habilitado por restrições originais; se futuro permitir, o padrão seria injetar contexto + instruções preservando placeholders.

### Segmentação e Chunking de Entradas Longas

Problema original: nós ou janelas extensas ultrapassavam limite de posições do modelo (ex.: 1024 tokens em m2m100), gerando warnings e potencial truncamento.

#### Solução Implementada
- `TranslationGateway.translate` agora mede `seq_len` inicial. Se `seq_len > max_pos`:
	1. Segmenta texto em sentenças por `get_sentence_segments`.
	2. Agrupa sentenças em chunks respeitando token budget cumulativo ≤ `max_pos`.
	3. Tradução chunk-a-chunk; junção com dois espaços preserva respiros.
- Sentenças muito longas (sozinhas > limite) sofrem truncação controlada (hard cutoff) para evitar index overflow.

#### Segmentação Sintática (spaCy)
- Nova função `spacy_sentence_split` tenta carregar modelos pequenos: `pt_core_news_sm`, `en_core_web_sm`, `es_core_news_sm` conforme `source_lang`.
- Se disponível, usa limites de sentença de spaCy para precisão sintática (evita quebra em abreviações: "art.").
- Fallback: `naive_sentence_split` por pontuação final.
- API pública usada pelo chunking: `get_sentence_segments(text, lang)`.

### Considerações de Performance

- Node dual-pass com RAG pode ser custoso: N chamadas de recuperação + N traduções baseline + N traduções adapted.
- Window dual-pass reduz chamadas de recuperação pelo agrupamento — número de janelas << número de nós.
- Recomenda-se usar RAG em node/window apenas quando granularidade fina de terminologia é necessária; caso contrário preferir doc/doc-sintatico.

### Persistência no Banco

Campos por nó após processamento dual-pass:
- `baseline_text`: resultado da primeira passagem sem contexto.
- `adapted_text`: tradução influenciada pelo contexto.
- `context_text`: contexto concatenado (quando adapted gerado). Vazio para baseline.
- `status_adapted`: `fresh` após salvar adapted; `pending` após baseline sozinho; `stale` usado para invalidar variantes em reprocessamentos.

### Limites e Próximos Passos (Possíveis Extensões)

- Ajustar `max_chars` das janelas (`build_windows`) dinamicamente em função de média de tokens por caractere (~3.5 para PT -> EN em m2m100).
- Cache de contexto por clusters de nós semanticamente semelhantes para reduzir chamadas RAG repetidas.
- Introdução de prompt estruturado para Google backend em node/window (se restrições forem relaxadas) preservando placeholders e instruções.
- Métrica automática de ganho RAG: comparar BLEU/termo exato baseline vs adapted em subconjunto jurídico anotado.

### Como Habilitar Segmentação spaCy

1. Instalar dependência (já adicionada a `requirements.txt`): `spacy`.
2. Baixar modelo PT (exemplo):
	 ```bash
	 python -m spacy download pt_core_news_sm
	 ```
3. (Opcional) modelos EN/ES se pretender segmentar textos fonte nesses idiomas.
4. Reexecutar pipeline; se modelo carregar com sucesso, chunking usará limites de sentença spaCy automaticamente.

### Resumo Rápido

| Modo          | Contexto | Dual-Pass | Segmentação Longa | Uso Recomendado |
|---------------|----------|-----------|-------------------|-----------------|
| node          | Nenhum / RAG por nó | Sim (se RAG) | Sentenças (spaCy/naive) | Ajustes terminológicos locais |
| window        | Local + RAG por janela | Sim (se RAG) | Sentenças (spaCy/naive) | Compromisso rapidez/coerência |
| doc           | Global + RAG completo | Sim (se RAG) | Não necessário (uma chamada) | Máxima coerência |
| doc-sintatico | Global + RAG + redistribuição | Sim (se RAG) | Não (redistribuição pós) | Coerência + fluidez em nós curtos |

---

Este documento deve ser mantido atualizado a cada ajuste estrutural para suportar análise no TCC sobre impacto de contexto recuperado em qualidade de tradução jurídica.

