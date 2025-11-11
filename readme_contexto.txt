
## Por que o backend Google (LLM) funcionou melhor?

- Contexto global: no modo “doc”, linearizamos o documento inteiro em segmentos marcados (<N0>…</N0>) e traduzimos tudo de uma vez. A LLM segue instruções para manter marcadores e placeholders, evitando perda de contexto que ocorria ao traduzir nó a nó.
- Robustez a ruído: marcadores <ph data-id="PHxxxx"> são estáveis e a LLM lida bem com tokens não linguísticos e rótulos isolados (“RELATOR”, “TRECHO”).
- Instrução de formato: o prompt exige preservar segmentos e não reordenar blocos, garantindo mapeamento de volta 1:1 para cada nó.

Em contraste, o modelo HF seq2seq m2m100 recebia fragmentos curtos (muitas vezes só um rótulo) e sem contexto, resultando em traduções degeneradas ou omissões. O doc-level com LLM reduz isso drasticamente.

## Visão geral da arquitetura

Fluxo de vida de um arquivo HTML:
1. Ingest (indexação):
	- Lê o HTML, percorre o DOM, adiciona `data-node-id` a blocos relevantes e extrai nós com placeholders inline sanitizados (<ph data-id="PHxxxx">…</ph>).
	- Persiste nós em SQLite (`data/db/nlp_tcc.sqlite`).
	- Salva HTML indexado em `data/extracted/<doc>_indexed.html`.
2. Tradução:
	- Estratégias: `node` (nó isolado), `window` (janelas de nós), `doc` (documento linearizado). Recomendado: `doc`.
	- Backends: `hf` (Hugging Face) ou `google` (Gemini). Recomendado: `google` + `doc` para qualidade.
	- No modo `doc`, criamos `<N0>texto</N0>\n<N1>texto</N1>...`, traduzimos e repartimos por nó.
3. Export:
	- HTML: reconstrói o DOM original decodificando placeholders para tags inline e inserindo o texto traduzido por nó.
	- TXT: concatena conteúdo por nó (ordenado) em `results/text/<doc>_<variant>_<lang>.txt` para avaliação offline.

Serviços principais:
- `dom_indexer.py`: indexa o DOM, gera nós e placeholders.
- `services/translation_service.py`: tradução `node` ou `window`.
- `services/doc_level_service.py`: tradução `doc` (linearização <N#> + parser inverso).
- `backends/hf_backend.py` e `backends/google_backend.py`: provedores de tradução.
- `services/export_service.py`: exporta HTML.
- `services/text_export_service.py`: exporta TXT.

## Como rodar

1) Instalar dependências (ambiente já configurado):

2) Definir chave do Google (opcional, para backend google):
- Crie `.env` na raiz com: `GOOGLE_API_KEY="sua_chave"` (já suportado por loader interno).

3) Processar e exportar (exemplos):
- Doc-level com Google:
  - `python scripts\mvp_cli.py process --input arquivos_juridicos\InteriorTeor30.html --languages en --backend google --mode doc`
  - `python scripts\mvp_cli.py export --doc InteriorTeor30 --language en --variant adapted`
- Exportar TXT para avaliação:
  - `python scripts\mvp_cli.py export-text --doc InteriorTeor30 --language en --variant adapted`

## API (protótipo)

Foi adicionado um app FastAPI (`src/api/app.py`):
- `POST /process` body: `{ input, language, source_lang, backend, mode }`
- `POST /export/html` body: `{ doc, language, variant, source_lang }`
- `POST /export/text` body: `{ doc, language, variant, source_lang }`
Para rodar: `uvicorn src.api.app:app --reload` (após instalar `fastapi` e `uvicorn`).

## Avaliação e comparações

Para comparar métodos:
- Gere TXT com `--backend hf --mode window` (baseline MT literal) e com `--backend google --mode doc` (LLM). Compare com tradução humana (salve em `results/text/<doc>_human_<lang>.txt`).
- Use métricas (ex.: BLEU via `sacrebleu`) e avaliação humana qualitativa.

## Como influenciar o método além de prompt engineering

1. RAG (Retrieval-Augmented Generation):
	- Construir um índice de contexto jurídico (glossário, definições, precedentes).
	- Para cada janela/doc, recuperar top-k trechos relevantes e inserir como “Contexto” no prompt antes dos segmentos <N#>.
	- Ferramentas: `sentence-transformers` (já no requirements) para embeddings; FAISS opcional para indexação.
	- Benefício: reduzir ambiguidades de termos jurídicos e regionalismos sem “hardcode” de glossário.

2. Segmentação e janelas semânticas:
	- Em vez de nós HTML, agrupar por parágrafo/sentença mantendo IDs de volta.
	- Menos fragmentação, mais contexto.

3. Heurísticas estruturais:
	- Mesclar nós curtos (ex.: cabeçalhos em caps com dois-pontos) ao bloco seguinte.
	- Detectar degeneração (repetição) e reprocessar com parâmetros alternativos.

4. Atenção/alinhamento (avançado):
	- Extrair atenções/token align para redistribuir tokens traduzidos entre nós quando necessário.

## Estrutura de diretórios relevante

- `scripts/mvp_cli.py`: CLI principal.
- `src/`: código-fonte (serviços, backends, API).
- `data/`: artefatos intermediários (HTML indexado, db sqlite).
- `results/html` e `results/text`: saídas.

## Notas de segurança
- Não comitar chaves de API. O loader de `.env` só define variáveis se não estiverem presentes no ambiente, e `.env` deve ser excluído do controle de versão.

- indexar nós textuais do HTML com identificadores estáveis;
- guardar esses nós no SQLite junto com os placeholders de marcação inline;
- traduzir cada nó de forma independente utilizando o modelo `facebook/m2m100_418M` via `transformers`;
- remontar o HTML traduzido sem alterar a hierarquia do DOM.

## Estrutura principal
- `arquivos_juridicos/`: documentos de entrada em HTML.
- `data/extracted/`: HTML indexado (com `data-node-id`) salvo após o ingest.
- `data/db/nlp_tcc.sqlite`: banco SQLite com documentos e nós traduzidos.
- `results/html/`: saídas exportadas por idioma/variante.
- `scripts/mvp_cli.py`: ponto de entrada da CLI.
- `src/`: código de produção (indexação, tradução, persistência e export).

## Instalação
```powershell
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install -r requirements.txt
```

## Comandos principais

Todos executados a partir da raiz do projeto.

### 1. Ingestão (indexar e persistir nós)
```powershell
python scripts\mvp_cli.py ingest --input arquivos_juridicos\InteriorTeor30.html --languages en --source-lang pt
```
Gera `data/extracted/InteriorTeor30_indexed.html`, popula o banco e registra os identificadores de cada nó.

### 2. Processamento (ingest + tradução)
```powershell
python scripts\mvp_cli.py process --input arquivos_juridicos\InteriorTeor30.html --languages en --device auto --fp16
```
Traduz cada nó com o modelo Hugging Face e salva o texto traduzido em `baseline_text`/`adapted_text` (mesmo valor na versão enxuta).

### 3. Exportação
```powershell
python scripts\mvp_cli.py export --doc InteriorTeor30 --language en --variant baseline
```
Reconstrói o HTML final em `results/html/InteriorTeor30_baseline_en.html`, preservando tags e posições originais.

## Componentes ativos
- `src/dom_indexer.py`: percorre o DOM, marca elementos-bloco com `data-node-id` e substitui tags inline por placeholders reversíveis.
- `src/html_io.py`: abstrações mínimas de leitura/gravação de HTML.
- `src/translate.py`: carrega o modelo `M2M100` (GPU opcional com `device_map="auto"`).
- `src/services/translation_service.py`: traduz um nó de cada vez, ignorando textos vazios.
- `src/services/export_service.py`: injeta traduções no HTML indexado original.
- `src/persistence/*`: camada SQLite para documentos e nós.

## Decisões atuais
- **Sem glossário/RAG/spaCy**: módulos antigos foram removidos para evitar dependências e ruído.
- **Placeholder inline obrigatório**: evita que a tradução quebre tags como `<strong>` ou `<a>`.
- **SQLite**: suficiente para rastrear versões por idioma em ambiente local.

## Próximos passos sugeridos
1. Adicionar testes unitários para `dom_indexer` e `ExportService` (garantir integridade do ciclo encode → translate → decode).
2. Revisar instruções passadas ao modelo para reforçar que tokens `[[PHXXXX]]` não devem ser alterados.
3. Implementar verificação pós-tradução que acusa placeholders perdidos ou tags desequilibradas antes da exportação.
