**Fluxos do Sistema**

**Upload e Processamento**
- **Entrada:** Arquivo HTML jurídico em português.
- **Passos:**
  - Frontend (`IndexPage.vue`) envia upload ao backend.
  - `process_controller.py` chama utilitários: `html_io.py` (leitura), `dom_indexer.py` (indexação DOM com IDs), `segmentation.py` (segmentação em nós).
  - `persistence.repos` grava documento e nós no banco (`db.py`).
  - Telemetria: eventos de início/progresso/fim via `telemetry.bus` → SSE.
- **Saídas:** Documento persistido, HTML indexado em `data/extracted/*_indexed.html`, nós cadastrados.

**Tradução (Baseline e Adapted)**
- **Entrada:** Documento selecionado, idioma alvo (`en`/`es`), modo (`doc`, `node`, `window`).
- **Baseline:**
  - `translation_controller.py` chama `translation_pipeline.py` para aplicar backend (`backends/google_backend.py`) sobre cada nó/segmento.
  - Sem contexto adicional além do próprio texto.
- **Adapted:**
  - Usa `rag.retriever` para recuperar contexto (glossário/corpus) com `top-k` configurável.
  - Aplica adaptações (terminologia, estilo) na tradução.
- **Saídas:** Variantes `baseline` e `adapted` em banco, com timestamps e metadados; telemetria em tempo real.

**Exportação (HTML/TXT)**
- **Entrada:** Documento, idioma, variante (`baseline`/`adapted`).
- **HTML:**
  - `export_controller.py` lê HTML original indexado (`read_html`) e nós traduzidos.
  - `HTMLExportService.export_variant` injeta a variante na estrutura DOM.
  - Grava em `results/html/{doc}_{variant}_{lang}.html`.
- **TXT:**
  - `TextExportService.export_variant_text` lineariza conteúdo e salva em `results/text/{doc}_{variant}_{lang}.txt`.
- **Frontend:** `IndexPage.vue` monta URL `http://localhost:8000/resultados/html/{filename}` e utiliza `HtmlViewer.vue` para exibir.

**Avaliação**
- **Entrada:** Variante selecionada e arquivo humano (`.txt` ou comparável) para referência.
- **Processo:** `evaluation_controller.py` chama `evaluation_service.py` para calcular métricas (BLEU, WER, PER, TER). Tokenização simples e normalizações aplicadas.
- **Saída:** JSON com métricas; frontend colore por limiares (`metricColor`).

**Glossário e Corpus (Contexto)**
- **Glossário:**
  - `glossary_controller.py` CRUD sobre entradas (`term_src`, `lang_src`, `term_tgt`, `lang_tgt`, `notes`).
  - Usado na tradução adaptada para substituições/terminologia controlada.
- **Corpus:**
  - `corpus_controller.py` CRUD sobre textos auxiliares (`text`, `language`, `tags`, `notes`).
  - Indexado para RAG; `rag_repos` e `rag.retriever` fazem recuperação por similaridade.

**RAG e Janelas**
- **Window Mode:**
  - Frontend permite definir `windowSize` para comparar/visualizar diffs por janela de tokens.
  - Backend pode utilizar contexto de vizinhança dos nós para melhorar consistência (adaptação estilística/local).
- **Top-K:**
  - Configurável no frontend; influencia quantos trechos são recuperados pelo RAG.

**Telemetria (SSE)**
- **Eventos:** Início, progresso (percentual, etapa), conclusão, erro.
- **Backend:** `telemetry.bus` publica; `telemetry.observer` transmite via SSE.
- **Frontend:** `IndexPage.vue` abre EventSource (es) em `iniciarSSE()` e acumula em `eventos` para exibição.

**Fluxo no Frontend**
- Usuário seleciona documento (`documents-store.js` carrega lista). 
- Realiza upload/processa; acompanha estado (`carregando`, `processamento`, `processando`).
- Seleciona idioma e dispara tradução; opcionalmente ajusta `ragTopk` e modo.
- Lista variantes e reexporta; visualiza HTML no `HtmlViewer.vue`.
- Avalia com arquivo humano e analisa métricas.
- Adiciona contexto (glossário/corpus) e reprocessa/adapta conforme necessário.

**Rotas e Endpoints Principais (Resumo)**
- `POST /processar`: Processar documento (indexar/segmentar/persistir).
- `POST /traduzir`: Traduzir (baseline/adapted) para idioma alvo.
- `POST /exportar/html`: Exportar HTML traduzido.
- `POST /exportar/texto`: Exportar TXT traduzido.
- `POST /avaliar`: Calcular métricas de avaliação.
- `GET /nos`: Listar nós/segmentos.
- `POST /glossario`: CRUD de termos.
- `POST /corpus`: CRUD de textos auxiliares.
- `GET /resultados/html/{arquivo}`: Servir arquivos exportados ao frontend.

**Boas Práticas e Convenções**
- Endpoints e documentação em português.
- Funções/classes preferencialmente com nomes em português; variáveis e libs podem permanecer em inglês.
- Arquivos de saída organizados por `doc`, `variant`, `lang` em `results/*`.
