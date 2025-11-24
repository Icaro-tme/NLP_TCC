# RAG em detalhes

Este guia destrincha o módulo de Retrieval-Augmented Generation (RAG) do projeto. Cada parte do fluxo é explicada com exemplos, comandos e motivos por trás de cada decisão.

---

## 1. Conceito geral

RAG combina duas etapas:

1. **Recuperação (Retrieval):** buscamos trechos relevantes em uma base de conhecimento externa (glossário e corpus).
2. **Geração (Generation):** o tradutor usa esses trechos como contexto adicional para produzir uma saída mais fiel.

O objetivo é garantir terminologia jurídica consistente e preservar o estilo do domínio. Sem RAG, o modelo pode optar por sinônimos indesejados ou ignorar nuances.

---

## 2. Componentes do sistema

| Componente | Função | Arquivo chave | Exemplo |
|------------|--------|---------------|---------|
| `DocLevelTranslationService` | Lineariza o documento com marcadores `<N#>...</N#>`, chama o backend de tradução e aplica RAG. | `src/services/doc_level_service.py` | `doc_service.translate_document(nodes, target_lang="en")` |
| `Retriever` | Constrói/carrega o índice, filtra por idioma, ranqueia trechos e monta o contexto final. | `src/rag/retriever.py` | `Retriever.retrieve(query_text, top_k=3, source_lang="pt", target_lang="en")` |
| Banco SQLite (`glossary_entries`, `corpus_snippets`) | Armazena termos e parágrafos aprovados pelo time. | `data/db/nlp_tcc.sqlite` | `SELECT term_src, term_tgt FROM glossary_entries;` |
| `rag_index.pkl` | Arquivo com embeddings pré-computados e metadados dos trechos (ver seção 4). | `data/rag_index/rag_index.pkl` | carregado/gravado por `Retriever.build_index()` |
| `last_context` | String com o contexto usado na última tradução; também persiste em `nodes.context_text`. | disponível após cada rodada | consulta via SQL (ver seção 6) |

---

## 3. Embeddings: o que são e por que usar

- Um **embedding** é uma representação numérica de um texto. Pense em uma lista de números (`[0.12, -0.04, ...]`) onde frases similares ficam próximas.
- Usamos o modelo multilingual `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, que entende PT/EN/ES.
- Fluxo:
  1. Cada termo do glossário e cada parágrafo do corpus é transformado em um embedding e guardado no índice.
  2. O texto linearizado do documento (até ~4000 caracteres) também é convertido em embedding durante a tradução.
  3. Calculamos similaridade (produto escalar) e retornamos os trechos com maior pontuação.

**Exemplo prático:**

- Corpus contém: "Ao homologar o termo de ajustamento de conduta..."
- Documento atual fala de TAC. O embedding do documento fica perto do embedding do trecho, então ele é recuperado e ajuda a reforçar a tradução de "termo de ajustamento de conduta".

---

## 4. `--rag-build-index` e o arquivo `rag_index.pkl`

### 4.1 Quando usar a flag

Adicionar a flag `--rag-build-index` na CLI faz com que o índice seja reconstruído **antes** de começar a traduzir. Use sempre que:

- Inserir novos termos no glossário ou parágrafos no corpus (via scripts, API ou importação manual).
- Limpar ou alterar significativamente as tabelas.
- Trocar o modelo de embeddings.

Sem a flag, o projeto reaproveita o último índice salvo. Se o arquivo estiver inválido (por exemplo, modelo diferente), o retriever acusa erro pedindo a reconstrução.

### 4.2 Estrutura do `rag_index.pkl`

- A extensão `.pkl` significa arquivo **pickle**, o formato binário padrão do Python para serializar objetos.
- Conteúdo principal:
  - `model_name`: nome do modelo de embeddings usado.
  - `documents`: lista de `RagDocument` com `doc_id`, texto formatado e `metadata` (idiomas, tags, tipo).
  - `embeddings`: matriz `numpy` com todos os vetores.

**Como inspecionar:**

```powershell
python - <<'PY'
import pickle, pathlib
index_path = pathlib.Path('data/rag_index/rag_index.pkl')
with index_path.open('rb') as fh:
    index = pickle.load(fh)
print('Modelo:', index.model_name)
print('Docs no índice:', len(index.documents))
print('Primeiro doc:', index.documents[0].doc_id, index.documents[0].metadata)
PY
```

Se `model_name` não bater com o modelo atual da configuração, o retriever lança `RuntimeError` orientando a rodar `--rag-build-index`.

---

## 5. Filtragem por idioma antes do ranking

Mesmo depois de construir o índice, nem todo documento é válido para qualquer tradução. O retriever aplica filtros antes de calcular a similaridade final:

- **Glossário:**
  - `metadata["lang_src"]` precisa ser igual à língua de origem (ou `"multi"`).
  - `metadata["lang_tgt"]` precisa ser igual à língua alvo.

- **Corpus:**
  - `metadata["language"]` deve ser igual à língua de origem **ou** à língua alvo.

Isso evita que, por exemplo, trechos em espanhol apareçam numa rodada pt→en. Esse comportamento vale tanto para o Hugging Face quanto para a Google API, garantindo contexto coerente com a direção da tradução.

---

## 6. Construção do contexto e `last_context`

### 6.1 Como o texto é montado

Depois de filtrar e ranquear, o retriever chama `build_context`, que gera uma string com cabeçalhos informativos:

```
[Fonte: glossary:42 | score=0.892 | langs=pt->en]
Termo (pt): medida cautelar
Tradução (en): interim relief

[Fonte: corpus:15 | score=0.741 | lang=pt | tags=infraestrutura,TAC]
Ao homologar o termo de ajustamento de conduta...
```

### 6.2 Onde fica salvo

1. **Em memória:** `DocLevelTranslationService.last_context` recebe a string logo após a recuperação.
2. **No banco:** o mesmo texto é gravado no campo `nodes.context_text` para cada nó traduzido naquela rodada.

**Como visualizar no SQLite:**

```powershell
sqlite3 data\db\nlp_tcc.sqlite "SELECT id, substr(context_text, 1, 200) || '...' FROM nodes WHERE context_text IS NOT NULL LIMIT 3;"
```

Isso mostra os primeiros 200 caracteres do contexto usado em alguns nós. Útil para auditoria e depuração.

---

## 7. Hugging Face, placeholders e “prompt alongado”

### 7.1 Desafio

Modelos seq2seq do Hugging Face (por exemplo, M2M100) esperam apenas o texto a traduzir. Não existe campo separado para “contexto adicional”. Se simplesmente concatenássemos o contexto ao texto, poderíamos:

- Quebrar a marcação `<N#> ... </N#>`.
- Extrapolar o limite de tokens de entrada.
- Diluir instruções (prompt alongado) e confundir o modelo.

### 7.2 Estratégia com placeholders

1. Extraímos pares do contexto (`medida cautelar → interim relief`).
2. Procuramos ocorrências no texto linearizado e substituímos por tokens `<<RAG0>>`, `<<RAG1>>`, etc.
3. Enviamos o texto modificado ao modelo.
4. Depois da tradução, restauramos cada token com a tradução alvo.

**Exemplo:**

```text
Original: <N0>O juiz manteve a medida cautelar.</N0>
Enviado ao HF: <N0>O juiz manteve a <<RAG0>>.</N0>
Resposta HF: <N0>The judge upheld the <<RAG0>>.</N0>
Final: <N0>The judge upheld the interim relief.</N0>
```

### 7.3 Resultado

- Terminologia controlada sem alterar o formato esperado pelo modelo.
- Menos risco de “prompt alongado” (prompt longo demais com instruções dispersas).

---

## 8. Google API e uso direto do contexto

Backends como Gemini aceitam prompts extensos. O projeto adiciona o contexto diretamente ao prompt junto com instruções fixas.

**Estrutura simplificada:**

```
Sistema: Você é um tradutor jurídico pt→en...
Usuário:
Contexto adicional:
[Fonte: ...]
Termo (pt): medida cautelar
Tradução (en): interim relief

Texto para traduzir:
<N0>O juiz manteve a medida cautelar...</N0>
```

O LLM decide como usar o contexto. Não precisamos de placeholders porque o modelo lida bem com prompts longos.

---

## 9. Rodando uma tradução com inspeção completa

### 9.1 Reconstruir e observar

```powershell
python .\scripts\mvp_cli.py process ^
  --input arquivos_juridicos\InteriorTeor30.html ^
  --languages en ^
  --mode doc ^
  --backend hf ^
  --rag-build-index ^
  --rag-topk 3 ^
  --observe
```

- `--rag-build-index`: reconstrói o índice antes de começar.
- `--observe`: salva eventos (incluindo `RagContextEvent`) no console ou em JSONL.

### 9.2 Conferir o índice depois da run

Use o snippet da seção 4.2 para imprimir informações básicas sobre `rag_index.pkl`.

### 9.3 Consultar o banco

```powershell
sqlite3 data\db\nlp_tcc.sqlite "SELECT term_src, term_tgt, lang_tgt FROM glossary_entries LIMIT 5;"
sqlite3 data\db\nlp_tcc.sqlite "SELECT substr(text,1,120) || '...', language FROM corpus_snippets LIMIT 5;"
sqlite3 data\db\nlp_tcc.sqlite "SELECT id, substr(context_text,1,200) || '...' FROM nodes WHERE context_text IS NOT NULL LIMIT 5;"
```

### 9.4 Comparar com RAG desligado

1. Rode com `--rag-topk 0`.
2. Exporte/observe o resultado.
3. Rode novamente com `--rag-topk 3`.
4. Compare `context_text` e a terminologia resultante para quantificar o impacto.

---

## 10. Manutenção do banco de conhecimento

### 10.1 Importar arquivos manuais

```powershell
sqlite3 data\db\nlp_tcc.sqlite "DELETE FROM glossary_entries;"
sqlite3 data\db\nlp_tcc.sqlite "DELETE FROM corpus_snippets;"
sqlite3 data\db\nlp_tcc.sqlite "DELETE FROM sqlite_sequence WHERE name IN ('glossary_entries','corpus_snippets');"
sqlite3 data\db\nlp_tcc.sqlite ".mode csv" ".separator |" ".import --skip 1 glossario/manual_entries.txt glossary_entries"
sqlite3 data\db\nlp_tcc.sqlite ".mode csv" ".separator |" ".import --skip 1 corpus/manual_notes.txt corpus_snippets"
```

### 10.2 Usando a API

- `POST /feedback/glossary`: adiciona termos com idiomas explícitos e invalida o índice.
- `POST /feedback/corpus`: grava parágrafos com `language` e `tags`, também invalidando o índice.
- `POST /nodes/{id}/human-translation`: registra traduções humanas homologadas.

### 10.3 Quando reconstruir o índice novamente?

- Após cada rodada de feedback relevante.
- Antes de execuções críticas (por exemplo, gerar entregas finais) para garantir que o índice contém as últimas atualizações.

---

## 11. Glossário rápido de termos

| Termo | Definição | Exemplo |
|-------|-----------|---------|
| **Embedding** | Vetor numérico que representa um texto. | `[0.11, -0.03, ...]` |
| **RAG index** | Estrutura com documentos + embeddings + metadados. | `rag_index.pkl` |
| **`.pkl`** | Extensão do `pickle`, formato binário de objetos Python. | `pickle.dump(obj, open('arquivo.pkl','wb'))` |
| **Contexto (`last_context`)** | Texto que acompanha a tradução. | `[Fonte: glossary:42 | ...]` |
| **Placeholder (`<<RAG0>>`)** | Token temporário para forçar terminologia no Hugging Face. | substitui "medida cautelar" |
| **Prompt alongado** | Prompt extenso que pode dispersar instruções ou atingir limites. | concatenar documento + longos anexos |
| **`--rag-build-index`** | Flag que gera o índice a partir do SQLite antes da tradução. | `process --rag-build-index` |

---

## 12. Checklist final

1. Atualizou glossário ou corpus? → Importe no SQLite e rode com `--rag-build-index`.
2. Precisa inspecionar o contexto usado? → Consulte `nodes.context_text` ou o log com `--observe`.
3. Hugging Face trocando termos? → Verifique os placeholders e o contexto retornado.
4. Dúvidas sobre o índice? → Use o snippet de inspeção do pickle ou reconstrua.

Seguindo este roteiro você terá uma visão clara de como o RAG funciona, por que cada decisão foi tomada e como acompanhar o impacto na tradução para qualquer backend.