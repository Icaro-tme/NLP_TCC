# Tradução HTML preservando estrutura

Este repositório concentra apenas o fluxo necessário para traduzir documentos HTML mantendo a estrutura original. A versão atual removeu todos os componentes de RAG, glossário e métricas automáticas; o pipeline agora foca em:

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
