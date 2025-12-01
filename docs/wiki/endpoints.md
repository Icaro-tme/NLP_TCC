**Endpoints Principais**

- `POST /processar`
  - **Descrição:** Processa um documento HTML (indexação + segmentação + persistência).
  - **Body (exemplo):**
    - `{ "doc": "InteriorTeor30", "language": "pt" }`
  - **Resposta:** `{ "status": "ok", "document_id": 123 }`

- `POST /traduzir`
  - **Descrição:** Executa tradução para idioma alvo; gera variantes `baseline` e/ou `adapted`.
  - **Body (exemplo):**
    - `{ "doc": "InteriorTeor30", "source_lang": "pt", "language": "en", "variant": "adapted", "mode": "doc", "rag_topk": 3 }`
  - **Resposta:** `{ "status": "ok", "variant": "adapted", "updated_at": "2025-12-01T12:00:00Z" }`

- `POST /exportar/html`
  - **Descrição:** Exporta HTML traduzido para `results/html` usando a variante selecionada.
  - **Body (exemplo):**
    - `{ "doc": "InteriorTeor30", "source_lang": "pt", "language": "en", "variant": "baseline" }`
  - **Resposta:** `{ "output": "results/html/InteriorTeor30_baseline_en.html" }`

- `POST /exportar/texto`
  - **Descrição:** Exporta texto linearizado `.txt` com a variante.
  - **Body (exemplo):**
    - `{ "doc": "InteriorTeor30", "source_lang": "pt", "language": "en", "variant": "adapted" }`
  - **Resposta:** `{ "output": "results/text/InteriorTeor30_adapted_en.txt" }`

- `POST /avaliar`
  - **Descrição:** Calcula métricas (BLEU, WER, PER, TER) comparando variante com arquivo humano.
  - **Body (exemplo):**
    - `{ "doc": "InteriorTeor30", "language": "en", "variant": "adapted" }` + arquivo humano anexado (upload multipart).
  - **Resposta:** `{ "BLEU": 0.42, "WER": 0.31, "PER": 0.28, "TER": 0.45 }`

- `GET /nos`
  - **Descrição:** Lista nós/segmentos do documento.
  - **Query (exemplo):** `?doc=InteriorTeor30&language=pt`
  - **Resposta:** `[ { "node_id": 1, "text": "..." }, ... ]`

- `POST /glossario`
  - **Descrição:** CRUD de termos para adaptação.
  - **Body (exemplo - criar):**
    - `{ "term_src": "ação", "lang_src": "pt", "term_tgt": "lawsuit", "lang_tgt": "en", "notes": "jurídico" }`
  - **Resposta:** `{ "id": 10, "status": "created" }`

- `POST /corpus`
  - **Descrição:** CRUD de textos auxiliares para RAG.
  - **Body (exemplo - criar):**
    - `{ "text": "Texto modelo de sentença...", "language": "pt", "tags": "sentenca,modelo", "notes": "fonte manual" }`
  - **Resposta:** `{ "id": 22, "status": "created" }`

- `GET /resultados/html/{arquivo}`
  - **Descrição:** Servir arquivo HTML exportado (usado pelo `HtmlViewer.vue`).
  - **Exemplo:** `GET /resultados/html/InteriorTeor30_adapted_en.html`

**Observações**
- Prefixos dos controladores seguem português (ex.: `/exportar`, `/avaliar`).
- Payloads exatos podem variar conforme `src/api/models/*`. Use os nomes `doc`, `source_lang`, `language`, `variant`, `mode`, `rag_topk` conforme definido.
- Respostas incluem caminhos relativos ao workspace (ver `PathsConfig`).
