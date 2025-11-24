# Planejamento Simplificado da Tradução HTML# Planejamento simplificado da tradução HTML



## Objetivo atual## Objetivo atual

- Processar um documento HTML, extraindo nós de texto com identificadores estáveis.- Traduzir documentos HTML mantendo a estrutura intacta.

- Traduzir cada nó com o modelo `facebook/m2m100_418M` (biblioteca `transformers`).- Usar apenas o modelo `facebook/m2m100_418M` (Hugging Face) via `transformers`.

- Reconstituir o HTML preservando a estrutura original e as tags inline.- Controlar nós extraídos por meio de identificadores determinísticos (`data-node-id`).

- Persistir dados mínimos em SQLite para suportar múltiplos idiomas por documento.- Persistir texto original e traduzido em SQLite e reconstruir o HTML.



## Fluxo resumido## Fluxo de alto nível

1. **Ingest (`scripts/mvp_cli.py ingest`)**1. **Ingest** (`scripts/mvp_cli.py ingest`)

   - Lê o HTML bruto e usa `src/dom_indexer.py` para aplicar `data-node-id` em elementos bloco.   - Lê HTML bruto.

   - Substitui tags inline por placeholders `[[PHXXXX]]` via `PlaceholderEncoder`.   - Marca elementos-bloco suportados (`p`, `li`, `h1`-`h4`, `td`, `th`, `caption`) com `data-node-id`.

   - Salva o HTML indexado em `data/extracted/<doc>_indexed.html` e persiste os nós em SQLite.   - Substitui tags inline por placeholders `[[PHXXXX]]` e salva metadados.

2. **Process (`scripts/mvp_cli.py process`)**   - Armazena nós e placeholders em SQLite.

   - Reexecuta a ingest se necessário.

   - Traduz cada nó chamando `TranslationService`, que delega ao `TranslationGateway` (modelo Hugging Face carregado sob demanda).2. **Process** (`scripts/mvp_cli.py process`)

   - Armazena o resultado nas colunas `baseline_text` e `adapted_text` (mesmo valor nesta versão).   - Reaproveita ingest.

3. **Export (`scripts/mvp_cli.py export`)**   - Traduz cada nó usando `TranslationGateway` (um modelo carregado por processo).

   - Carrega o HTML indexado, encontra cada `data-node-id` e substitui o conteúdo pelo texto traduzido.   - Persiste o resultado em `baseline_text` e `adapted_text`.

   - Utiliza `ExportService` para restaurar placeholders como tags reais.

   - Escreve o resultado em `results/html/<doc>_<variant>_<lang>.html`.3. **Export** (`scripts/mvp_cli.py export`)

  - Lê o HTML indexado salvo em `data/extracted`.

## Componentes ativos  - Percorre elementos com `data-node-id`, substitui conteúdo pelo texto traduzido e reidrata tags inline a partir dos placeholders.

- `src/core/config.py`: define `TranslationConfig`, `PathsConfig` e `PipelineConfig`.  - Escreve o HTML final em `results/html`.

- `src/core/placeholders.py`: encode/decode de tags inline com placeholders determinísticos.

- `src/core/logging_utils.py`: logger e medição de tempo simples.## Componentes mantidos

- `src/dom_indexer.py`: percorre o DOM e gera metadados de nós.- `src/core/config.py`: dataclasses com opções de tradução e caminhos.

- `src/html_io.py`: leitura/gravação de HTML com UTF-8.- `src/core/placeholders.py`: encode/decode de tags inline.

- `src/translate.py`: wrapper para carregar o modelo Hugging Face e gerar traduções.- `src/core/logging_utils.py`: logging básico com medição de tempo.

- `src/services/translation_service.py`: traduz cada nó ignorando textos vazios.- `src/dom_indexer.py`: indexação do DOM + placeholders.

- `src/services/export_service.py`: reconstrói o HTML final a partir das traduções salvas.- `src/html_io.py`: leitura e escrita de HTML.

- `src/persistence/db.py`: inicializa o SQLite (`documents` e `nodes`).- `src/translate.py`: wrapper para carregamento do modelo Hugging Face (GPU opcional).

- `src/persistence/repos.py`: operações CRUD para documentos e nós.- `src/services/translation_service.py`: orquestra tradução de um nó.

- `scripts/mvp_cli.py`: CLI com subcomandos `ingest`, `process` e `export`.- `src/services/export_service.py`: reconstrói HTML traduzido.

- `src/persistence/db.py` e `src/persistence/repos.py`: acesso ao SQLite.

## Esquema do banco (SQLite)- `scripts/mvp_cli.py`: CLI com os subcomandos `ingest`, `process`, `export`.

- **documents**: `id`, `name`, `lang_src`, `lang_tgt`, `sha256`, `created_at`.

- **nodes**: `id`, `document_id`, `node_path`, `tag`, `attrs`, `original_text`, `baseline_text`, `adapted_text`, `human_text`, `placeholders`, `status_adapted`, `status_human`, `context_text`.## Componentes removidos

- Glossário, RAG, pós-processamento heurístico, métricas e integrações spaCy.

## Pontos de atenção- Scripts auxiliares antigos (`pipeline.py`, `evaluate_translations.py`, `generate_references.py`, `_debug_load_model.py`).

- Garantir que traduções mantenham placeholders intactos; caso contrário deverá ser sinalizado antes da exportação.- Stubs (`src/preproc.py`, `src/postproc.py`, `src/rag.py`, `src/nlp_signals.py`, `src/services/glossary_service.py`, `src/services/rag_service.py`, `src/core/context.py`, `src/core/prompt_builder.py`).

- O diretório `glossario/` permanece apenas como referência histórica e não é utilizado pela versão atual.

- Documentos muito longos podem exigir paginação manual para evitar estouro de memória durante a tradução.## Estrutura de pastas (24/11/2025)

```

## Backlog imediatoarquivos_juridicos/

1. Adicionar testes unitários para `dom_indexer` e `ExportService` (ciclo encode → decode).data/

2. Criar validação após a tradução para verificar se todos os tokens `[[PHXXXX]]` estão presentes.  extracted/

3. Automatizar a criação do banco (`data/db/nlp_tcc.sqlite`) em ambientes limpos (script ou comando Make/PowerShell).  db/

4. Considerar logging adicional com contagem de nós traduzidos por idioma e tempo médio por nó.glossario/                 # mantido apenas como referência (não utilizado)

5. Revisar documentação do README sempre que novas flags da CLI forem adicionadas.results/

  html/
scripts/
  mvp_cli.py
src/
  core/
    config.py
    logging_utils.py
    placeholders.py
  dom_indexer.py
  html_io.py
  persistence/
    db.py
    repos.py
  services/
    export_service.py
    translation_service.py
  translate.py
```

## Backlog imediato
1. Verificar e registrar placeholders perdidos após a tradução (sanity check em `TranslationService`).
2. Adicionar testes unitários para `dom_indexer` e `ExportService`.
3. Configurar lint/format (ex.: `ruff` ou `black`) para manter consistência.
4. Introduzir camada de validação antes de subir HTML final (evitar estruturas quebradas).
5. Parametrizar `target_langs` e `model_name` via CLI/arquivo `.env`.

## Decisões futuras (fora do escopo atual)
- Reintroduzir glossário e RAG quando a versão estável de tradução estiver comprovada.
- Implementar revisão humana (`human_text`) e histórico por nó.
- Oferecer API/serviço ou interface web para processamento em lote.
    evaluate_translations.py
    generate_references.py
    mvp_cli.py                          # CLI unificada (novo)
```

Observação: manteremos `pipeline.py` funcional enquanto migramos, chamando funções de `src/`. O CLI novo (`mvp_cli.py`) orquestra o fluxo por documento, por nó, e export.

## Modelo de Dados (SQLite)

Tabela `documents`
- id (PK)
- name (str) — nome base do arquivo
- lang_src (str) — ex.: "pt"
- created_at (timestamp)
- sha256 (str) — do HTML original

Tabela `nodes`
- id (PK)
- document_id (FK → documents)
- node_path (str) — ex.: "0.2.5"
- tag (str) — ex.: "p"
- attrs_hash (str) — hash dos atributos relevantes
- original_text (text)
- baseline_text (text, null)
- adapted_text (text, null)
- human_text (text, null)
- status_adapted (enum: fresh|stale|null)
- status_human (enum: none|edited)

Tabela `glossary_terms`
- id (PK)
- lang_src (str)
- lang_tgt (str)
- term_src (str)
- term_tgt (str)
- flags (json) — {force_translate: bool, do_not_translate: bool}
- scopes (json) — ["address", "header", ...]

Tabela `rag_chunks`
- id (PK)
- text (text)
- meta (json)
- embedding (blob/array serializada)

Tabela `rag_links`
- node_id (FK)
- chunk_id (FK)
- score (float)

SQL de criação (exemplo simplificado):
```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  lang_src TEXT NOT NULL,
  sha256 TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nodes (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  node_path TEXT NOT NULL,
  tag TEXT,
  attrs_hash TEXT,
  original_text TEXT NOT NULL,
  baseline_text TEXT,
  adapted_text TEXT,
  human_text TEXT,
  status_adapted TEXT,
  status_human TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE glossary_terms (
  id INTEGER PRIMARY KEY,
  lang_src TEXT,
  lang_tgt TEXT,
  term_src TEXT,
  term_tgt TEXT,
  flags TEXT,
  scopes TEXT
);

CREATE TABLE rag_chunks (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  meta TEXT,
  embedding BLOB
);

CREATE TABLE rag_links (
  node_id INTEGER,
  chunk_id INTEGER,
  score REAL,
  FOREIGN KEY(node_id) REFERENCES nodes(id),
  FOREIGN KEY(chunk_id) REFERENCES rag_chunks(id)
);
```

### Estados e definições (o que é um nó "stale")

- `status_adapted`:
  - `fresh`: a tradução adaptada reflete as regras atuais (glossário/RAG/configs vigentes) para o texto original armazenado.
  - `stale`: a tradução adaptada pode estar desatualizada porque algo mudou (ex.: glossário, regras, RAG, configs) OU o `original_text` foi reextraído; requer retradução.
  - `null`: ainda não foi gerada tradução adaptada.

- `status_human`:
  - `none`: sem edição humana registrada.
  - `edited`: existe `human_text` vigente para o nó.

Quando marcamos nós como "stale", eles entram na fila de reprocessamento seletivo (não precisamos retraduzir o documento inteiro). Exemplos de gatilhos: atualização do glossário, alteração de regras, mudança de configuração de prompt, reindexação do DOM que altere placeholders.

## Fluxo de Execução do MVP

1) Ingestão de HTML
- Criar `document` (DB), calcular hash, armazenar HTML original (arquivo) e criar `nodes` com `original_text` percorrendo DOM e gerando `node_path` + placeholders.

2) Tradução baseline/adaptada
- Para cada `node`:
  - Pré-processar texto (caps rules + domain rules + preferências de glossário no source).
  - Baseline: traduzir sem contexto.
  - Adaptada: montar prompt com instrução anti-reordenação + contexto RAG (top_k=1) e traduzir.
  - Pós-processar (recolocar placeholders; enforce de glossário no target).
  - Persistir `baseline_text` e `adapted_text`; `status_adapted=fresh`.

3) Export HTML
- Gerar `{doc}_baseline_{lang}.html`, `{doc}_adapted_{lang}.html`, `{doc}_human_{lang}.html` (se houver human_text; se não, copia adapted por padrão para visualização inicial).

4) Edição humana por nó (CLI inicialmente)
- Comando para listar nós, abrir um nó e gravar `human_text`.
- Retradução seletiva (ex.: nós afetados após glossário mudar) — marca `status_adapted=stale` e reprocessa.

5) Avaliação (document-level)
- `scripts/evaluate_translations.py` compara baseline/adapted com referência humana consolidada (human_html → texto concatenado ou referência externa).

## Heurísticas e Prompt (detalhe)

- Caps rules:
  - Se token ALL CAPS com 3+ chars e não estiver em `do_not_translate`, normalizar para Title Case antes da MT.
  - `force_translate` substitui no pós-processamento (com cuidado de palavras-fronteira).
- Domain rules:
  - Primeira linha/cabeçalho de endereço (padrões com CEP/SCES) aplica mapeamentos específicos (trecho→section, bairro→district etc.).
- Prompt adaptado:
  - "Traduza apenas o trecho abaixo. Use o contexto apenas para esclarecer termos; NÃO adicione, reordene ou resuma o texto original.\n\nTEXTO:\n{texto}\n\nCONTEXTO (apenas referência):\n{contexto}".

### Engenharia de Prompt (engineered prompting) vs. fine-tuning

- O que é: desenhar instruções e formato de entrada/saída para guiar um modelo pré-treinado a um comportamento específico, sem treinar novos pesos. Inclui instruções claras (não reordenar, não resumir), delimitação de contexto, e escolhas conservadoras (RAG top_k=1, contexto curto e limpo).
- Neste projeto: usamos prompts com instrução anti-reordenação e contexto opcional minimalista para resolver termos ambíguos, priorizando fidelidade ao texto de origem.
- Na primeira arquitetura: já utilizávamos um prompt simples e, em alguns momentos, concatenamos contexto de forma menos controlada (o que gerou risco de “prefixo/explicação” indesejada). Agora formalizamos e isolamos a construção do prompt via `PromptBuilder` e reduzimos o RAG para mitigar vazamentos.
- Diferença para fine-tuning: engineered prompting não altera os pesos do modelo; é uma camada de orquestração e regras. Fine-tuning/LoRA envolve treinar e salvar pesos/adapter próprios (futuro opcional).

### Propriedade e portabilidade do modelo e do sistema

- Modelo base: usamos um modelo pré-treinado do Hugging Face (por exemplo, `facebook/m2m100_418M`) sem fine-tuning. Não “possuímos” os pesos, mas possuímos a aplicação (código) e os dados (glossário, RAG, banco SQLite, regras, prompts).
- O “nosso modelo” no MVP é o sistema: pipeline + regras + dados persistidos, que produz traduções reproduzíveis dado o mesmo ambiente e versões.
- Portabilidade:
  - Código e dados via repositório + `data/db/nlp_tcc.sqlite` + `glossario/` + `corpus/definicoes/`.
  - Pesos do modelo são baixados do Hugging Face no primeiro uso (cache local). Podemos fazer um "snapshot" opcional em `models/` para operar offline.
  - Reprodutibilidade: fixar versões em `requirements.txt` (torch/transformers/accelerate/sentence-transformers) e documentar o seed/configs. Assim conseguimos mover entre máquinas e reproduzir resultados.
- Evolução futura para “modelo nosso” de fato: ao aplicar LoRA/PEFT, salvamos adapters/weights próprios (arquivos `.safetensors`) e versionamos no repositório ou em artefatos. A partir daí, sim, teremos um artefato de modelo proprietário além do código.

## Scripts de Terminal (MVP)

- Ingestão + processamento completo (um documento):
```powershell
# Criar o doc, indexar nós, traduzir baseline/adaptada e exportar HTMLs
python scripts/mvp_cli.py process --input arquivos_juridicos/InteriorTeor30.html --languages en,es --device cuda --fp16 --rag --rag-topk 1
```

- Editar um nó específico e reexportar:
```powershell
# Listar nós
python scripts/mvp_cli.py list-nodes --doc InteriorTeor30 --lang en
# Editar
python scripts/mvp_cli.py edit-node --doc InteriorTeor30 --lang en --path 0.2.5 --text "Edited text here"
# Exportar HTML atualizado humano
python scripts/mvp_cli.py export --doc InteriorTeor30 --lang en --variant human
```

- Avaliar documento (BLEU/TER e termos):
```powershell
python scripts/evaluate_translations.py InteriorTeor30 en
```

Observação: enquanto `mvp_cli.py` não existir, podemos mapear esses fluxos no `pipeline.py` atual chamando funções de `src/`.

## Pontos de Extensão (para depois)
- POS/NER (spaCy): módulo `nlp_signals` pode popular `pos_tags`/`named_entities` por nó e ativar regras baseadas em classe gramatical.
- Frontend reativo: API (FastAPI) + UI para edição por nó com toggle de variantes. O export HTML permanece como recurso adicional.
- Treinos leves (LoRA/PEFT): consumir pares (original→human) versionados e gerar um modelo especializado jurídico.
- Persistência Postgres e fila de jobs (Celery/RQ) para escalar.

## Critérios de Aceite do MVP
- [ ] Indexar nós de um HTML e persistir `original_text` no DB.
- [ ] Gerar `baseline_text` e `adapted_text` para todos os nós (en, es) com RAG top_k=1 e instrução anti-reordenação.
- [ ] Exportar HTMLs separados preservando a estrutura e os estilos (baseline/adapted/human).
- [ ] Permitir gravar `human_text` por nó e reexportar human HTML.
- [ ] Calcular métricas por documento (BLEU/TER e precisão de termos) usando as versões persistidas.

## Riscos e Mitigações
- Vazamento de contexto no adapted → instrução explícita, top_k=1, limpeza de trechos RAG.
- ALL CAPS tratados como nomes próprios → caps rules + force/do-not-translate.
- Desalinhamento de placeholders → testes unitários simples para casos inline (negrito/itálico/links).
- Mudanças de DOM entre ingestão e export → data-node-id, fallback por path e validação de checksum (futuro).

## Próximos Passos (ordem de implementação)
1) `src/persistence` (SQLite schema + repos) e `src/dom_indexer` (mapeamento e placeholders).
2) `src/core` (config/context/prompt/placeholders/logging) e serviços (`services/*`).
3) `src/translate` + `src/preproc` + `src/postproc` com regras e prompt adapted (usando serviços/core).
4) `src/html_io` (carregar/salvar + data-node-id) e export dos três HTMLs.
5) `scripts/mvp_cli.py` com comandos process/list-nodes/edit-node/export.
6) Integração com `scripts/evaluate_translations.py` para métricas por documento.
7) Ponto de extensão `nlp_signals` (stub) para spaCy futuro.

---

Este documento guia a implementação. Qualquer divergência encontrada na prática (performance/compatibilidade) será registrada aqui com o ajuste decidido e o porquê.
