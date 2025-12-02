**Visão Geral**
- **Stack:** Backend em `Python` (FastAPI), serviços auxiliares e utilitários; Frontend em `Vue 3` com `Quasar Framework` (JS/TS opcional), HTML/CSS.
- **Objetivo:** Processar documentos jurídicos em HTML (português), indexar e traduzir para inglês/espanhol, exportar versões, avaliar qualidade e permitir adaptação com contexto (glossário/corpus), com telemetria em tempo real.

**Arquitetura**
- **Camadas:**
  - **API (`src/api`)**: Endpoints FastAPI em português; controla upload/processamento, tradução, exportação, avaliação, glossário, corpus, nós, e processos.
  - **Serviços (`src/services`)**: Implementações de negócio (pipeline de tradução, exportações, avaliação).
  - **Persistência (`src/persistence`)**: Acesso a banco e repositórios (documentos, nós, RAG).
  - **Core (`src/core`)**: Configuração de caminhos, logging/utilitários, placeholders.
  - **RAG (`src/rag`)**: Recuperação auxiliar de contexto (retriever, utils) para tradução adaptada.
  - **Telemetria (`src/telemetry`)**: Barramento de eventos, contexto, observadores (SSE para frontend).
  - **Utilitários (`src/*.py`)**: `html_io.py` (IO HTML), `dom_indexer.py` (indexação DOM), `segmentation.py` (segmentação), `translate.py` (tradução utilitária).
  - **Frontend (`frontend_repo/interface`)**: SPA Vue/Quasar para interação, visualização, controle de processos e exportações.

**Diagrama de Componentes (Mermaid)**
```mermaid
flowchart LR
  subgraph Frontend [Frontend (Vue/Quasar)]
    UI[IndexPage.vue]
    Store[documents-store.js]
    Viewer[HtmlViewer.vue]
    SSE[EventSource]
  end

  subgraph API [FastAPI]
    PROC[process_controller]
    TRAD[translation_controller]
    EXP[export_controller]
    EVAL[evaluation_controller]
    GLOSS[glossary_controller]
    CORP[corpus_controller]
    NODE[node_controller]
  end

  subgraph Services [Serviços]
    PIPE[translation_pipeline]
    EXPHTML[HTMLExportService]
    EXPTXT[TextExportService]
    METR[evaluation_service]
  end

  subgraph Persistência
    DB[(SQLite)]
    REPOS[repos]
    RAGREPO[rag_repos]
  end

  subgraph RAG
    RETR[retriever]
    RUTILS[utils]
  end

  subgraph Telemetria
    BUS[bus]
    OBS[observer]
    EVTS[events]
  end

  subgraph Util
    IO[html_io]
    IDX[dom_indexer]
    SEG[segmentation]
    TRNS[translate]
    GGL[google_backend]
  end

  UI -->|HTTP| API
  Store -->|HTTP| API
  Viewer -->|GET resultados/html| API
  SSE -->|/sse| OBS

  PROC --> IO
  PROC --> IDX
  PROC --> SEG
  PROC --> REPOS
  REPOS --> DB

  TRAD --> PIPE
  PIPE --> TRNS
  TRNS --> GGL
  PIPE --> RETR
  RETR --> RAGREPO
  RAGREPO --> DB

  EXP --> EXPHTML
  EXP --> EXPTXT
  EXPHTML --> IO
  EXPTXT --> IO

  EVAL --> METR

  API --> BUS
  BUS --> OBS
```

**Detalhamento por Módulo (Backend)**
- `src/api/app.py`: Inicializa FastAPI, registra controladores, configura CORS e rotas de resultados (exposição de arquivos exportados). Base dos endpoints.
- `src/api/controllers/*.py`:
  - `base_controller.py`: Base para definir prefixos e tags em português; agrega `APIRouter` e helpers.
  - `process_controller.py`: Orquestra processamento de um documento (indexação, segmentação, persistência de nós), cria registros no banco, prepara para tradução.
  - `translation_controller.py`: Dispara pipeline de tradução (baseline/adapted), consulta repositórios, escreve variantes.
  - `export_controller.py`: Exporta variantes para HTML/TXT; lê HTML original indexado; usa `HTMLExportService`/`TextExportService`.
  - `evaluation_controller.py`: Avalia qualidade (BLEU, WER, PER, TER) comparando variante com arquivo humano.
  - `node_controller.py`: Operações sobre nós (listar, atualizar, inspecionar janelas/segmentos).
  - `glossary_controller.py`: CRUD de glossário (termos fonte/target com notas e idiomas) para adaptar tradução.
  - `corpus_controller.py`: CRUD de corpus auxiliar (texto, idioma, tags) para RAG e adaptação.
  - `feedback_controller.py`: Recebe feedback do usuário e persiste para ajuste futuro.
  - Modelos em `src/api/models/*.py` definem `pydantic` schemas usados pelos controladores (ex.: `ExportRequest`).
- `src/services/translation_pipeline.py`: Pipeline de tradução em etapas (carrega nós, aplica tradução com backend, adapta com glossário/corpus via RAG, grava variantes e telemetria). Responsável por baseline e adapted.
- `src/services/export_service.py` e `text_export_service.py`: Montagem de HTML/TXT linearizado com a variante escolhida; mantém metadados e estrutura básica do documento.
- `src/services/evaluation_service.py`: Cálculo de métricas de avaliação (BLEU/WER/PER/TER), tokenize, normalização e comparação.
- `src/persistence/db.py`: Acesso ao banco (SQLite por padrão), conexão e migrações leves.
- `src/persistence/repos.py`: Repositórios para documentos e nós (CRUD, queries por idioma, variante, estado).
- `src/persistence/rag_repos.py`: Armazena/consulta índices RAG, fontes de contexto (glossário/corpus), e resultados de recuperação.
- `src/core/config.py`: `PathsConfig` com diretórios (`data/extracted`, `results/html`, `results/text`, `db`), leitura de `.env`/config e criação de paths.
- `src/core/logging_utils.py`: Configuração de logs; integra com telemetria.
- `src/core/placeholders.py`: Valores padrão e símbolos utilitários.
- `src/rag/retriever.py`: Recupera trechos relevantes (top-k) a partir de fontes (glossário/corpus) para adaptação.
- `src/rag/utils.py`: Funções de apoio (similaridade, normalização, chunking).
- `src/telemetry/bus.py`: Barramento de eventos; publica eventos de processamento/tradução/exportação.
- `src/telemetry/context.py`: Define contexto de execução (documento, idioma, variante, timestamps, usuário). 
- `src/telemetry/events.py`: Tipos de evento (INICIADO, PROGRESSO, CONCLUIDO, ERRO, etc.).
- `src/telemetry/observer.py`: Observador que envia via SSE para o frontend; coleta e formata eventos.
- Utilitários:
  - `html_io.py`: Leitura/escrita de HTML, normalização de encoding, extração de texto.
  - `dom_indexer.py`: Indexa elementos DOM com IDs estáveis; salva `*_indexed.html` em `data/extracted`.
  - `segmentation.py`: Segmenta o documento em blocos/traduções unitárias (parágrafos, títulos, listas). 
  - `translate.py`: Interface simplificada para backends de tradução (Google, etc.).
- Backends:
  - `src/backends/google_backend.py`: Integração com API/serviços de tradução do Google; usado na baseline e como base para adapted com contexto adicional.

**Detalhamento (Frontend)**
- `frontend_repo/interface/src`:
  - `pages/IndexPage.vue`: Tela principal; controla upload/processamento, seleção de documento, modo (`doc`, `node`, `window`), idioma (`pt`→`en`/`es`), RAG `topk`, exportação de variantes, avaliação com arquivo humano, exibição de métricas, e logs via SSE.
  - `components/HtmlViewer.vue`: Visualizador de HTML exportado, carrega via URL construída (ex.: `http://localhost:8000/resultados/html/...`).
  - `stores/documents-store.js`: Store que chama endpoints do backend (listar documentos, processar, listar variantes, exportar, avaliar).
  - `boot/axios.js`: Configura Axios; base URL do backend.
  - `layouts/MainLayout.vue`: Layout de navegação; define cabeçalho/rodapé.
  - `router/*`: Rotas da SPA.
  - `css/*`: Estilos (Quasar variables, app.scss).

**Diretórios de Dados e Resultados**
- `data/extracted`: HTML indexado por `dom_indexer.py` (ex.: `InteriorTeor30_indexed.html`).
- `results/html`: Saídas de exportação por variante/idioma (acessadas pelo frontend).
- `results/text`: Saídas linearizadas `.txt` por variante/idioma.
- `data/rag_index`: Índices para recuperação (se aplicável).
- `glossario/manual_entries.txt` e `corpus/manual_notes.txt`: Fontes humanas para adaptação.

**Responsabilidades Principais**
- **Controladores (API):** Validar requisições, orquestrar serviços, mapear URIs em português, lidar com erros HTTP.
- **Serviços:** Implementar regras de negócio (tradução, exportação, avaliação) e publicar telemetria.
- **Persistência:** Fornecer acesso consistente a dados (documentos, nós, variantes, índices RAG, glossário, corpus).
- **RAG/Adaptação:** Enriquecer tradução com contexto recuperado de glossário/corpus (top-k/janelas).
- **Telemetria:** Emitir eventos para feedback ao usuário durante processos longos.
- **Frontend:** Expor operações, estado (carregando/processando), seleção de variantes, visualização e avaliação.

**Execução e Desenvolvimento**
- Backend (FastAPI):
  - Comando (exemplo): `python -m uvicorn src.api.app:app --reload`
  - Endpoints em `/processar`, `/traduzir`, `/exportar`, `/avaliar`, `/glossario`, `/corpus`, `/nos`, etc. (prefixos em português).
- Frontend (Quasar):
  - Instalar dependências em `frontend_repo/interface`: `npm install`
  - Desenvolvimento: `npx quasar dev`
  - Base do backend: `http://localhost:8000`

**Observações de Estilo e Idioma**
- Endpoints e documentação em português; nomes de funções/classes preferencialmente em português conforme instruções do projeto.
- Variáveis e referências de bibliotecas podem manter convenções em inglês.
