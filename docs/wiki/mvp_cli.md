# CLI do MVP (scripts/mvp_cli.py)

Esta página descreve o fluxo do script de linha de comando que orquestra o MVP.

Sumário
- Conceitos e termos
- Subcomandos e fluxo
- Ingestão (ingest)
- Processamento (process)
- Exportação de HTML (export)
- Exportação de texto (export-text)
- Ligações com outros módulos

## Conceitos e termos

- Nó (node): trecho textual extraído do DOM do HTML que será traduzido individualmente.
- Placeholder `<ph>`: marcador inline que preserva conteúdo/variáveis na tradução.
- Estratégias (mode):
  - node: tradução nó-a-nó (isolada).
  - window: janelas de contexto local; traduz como bloco e divide de volta.
  - doc: documento linearizado com marcadores `<N#>…</N#>`; traduz de uma vez e mapeia de volta.
- Backends (backend): `hf` (Hugging Face, seq2seq) e `google` (LLM Gemini, com prompt).
- RAG: recuperação de trechos relevantes (glossário/corpus) para compor contexto adicional.

## Subcomandos e fluxo

O script expõe 4 subcomandos:

1) ingest
   - Lê o HTML de entrada.
   - Indexa nós (com placeholders) e salva um HTML indexado em `data/extracted`.
   - Persiste no SQLite: documento(s) por idioma e todos os nós.

2) process
   - Executa ingest (se necessário) e, para cada idioma alvo, aplica a estratégia selecionada.
   - Modo doc com backend Google pode usar RAG: recupera trechos (glossário/corpus) e injeta no prompt.
   - Salva a tradução de cada nó no SQLite.

3) export
   - Reabre o HTML indexado (de `data/extracted`).
   - Carrega as traduções do SQLite e reconstrói o HTML com a variante selecionada (baseline/adapted/human).
   - Salva em `results/html/NOME_VARIANTE_IDIOMA.html`.

4) export-text
   - Similar ao export, mas gera um `.txt` linearizado em `results/text/...`.

## Ingestão (ingest)

- Entrada: caminho para o HTML; idiomas destino.
- Saídas:
  - `data/extracted/NOME_indexed.html`
  - Registros no SQLite: tabela de documentos (um por idioma) e tabela de nós (todos os segmentos).
- Objetivo: permitir reprocessar/exportar sem reindexar e armazenar traduções por nó/idioma.

Links relacionados: [Indexação de DOM](../PLACEHOLDER_dom_indexer.md)

## Processamento (process)

- Estratégias:
  - node: menos contexto, mais simples.
  - window: melhor qualidade local, ainda rápido.
  - doc: melhor qualidade geral (com LLM) mantendo estrutura via marcadores `<N#>`.
- Backends:
  - hf: modelo seq2seq; não consome `contexto` (RAG) nesta versão.
  - google: LLM; recebe `contexto` (quando RAG ativo) no prompt.
- RAG (opcional):
  - Constrói/usa um índice de embeddings (glossário/corpus) para recuperar `top_k` trechos.
  - Concatena trechos respeitando `max_context_chars` e injeta no prompt do LLM.
  - Para HF, RAG não está implementado (ver limitações e próximos passos).
  
- Restrição importante: backend `google` só deve ser usado com modo `doc`. A CLI bloqueia outras
    combinações, a menos que o usuário passe `--force` (o que consome muitos tokens e ignora o prompt
    otimizado para doc-level).

Links relacionados: [Serviço Doc-Level](../PLACEHOLDER_doc_level_service.md), [RAG Retriever](../PLACEHOLDER_rag_retriever.md)

## Exportação de HTML (export)

- Requer que o HTML indexado exista em `data/extracted`.
- Busca o documento por `nome base + idiomas` no SQLite para localizar os nós e suas traduções.
- Reconstrói o HTML preservando estrutura e placeholders.

Links relacionados: [ExportService](../PLACEHOLDER_export_service.md)

## Exportação de texto (export-text)

- Gera `.txt` com o conteúdo traduzido (útil para avaliação e comparação).

Links relacionados: [TextExportService](../PLACEHOLDER_text_export_service.md)

## Ligações com outros módulos

- Logging: `src/core/logging_utils.py` (PLACEHOLDER_logging.md)
- Persistência/DB: `src/persistence` (PLACEHOLDER_persistence.md)
- Backends: `src/backends` (PLACEHOLDER_backends.md)
- Serviços: `src/services` (PLACEHOLDER_services.md)
