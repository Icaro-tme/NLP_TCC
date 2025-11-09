# Tradução Automática Sensível ao Contexto Jurídico

Este repositório sustenta a prova de conceito do TCC: demonstrar que uma pipeline de tradução automática enriquecida por conhecimento jurídico consegue entregar traduções mais precisas do que abordagens literais. O foco está em combinar modelos pré-treinados, glossários especializados e recuperação de contexto (RAG) para tratar termos ambíguos do português jurídico ao traduzir para inglês e espanhol.

## Arquitetura do Projeto
- `arquivos_juridicos/`: origem em HTML (documentos jurídicos brutos).
- `data/html_raw/`: cópias organizadas dos HTMLs usados na prova.
- `data/extracted/`: textos limpos extraídos dos HTMLs.
- `data/references/`: traduções de referência (curadas manualmente) para avaliação.
- `glossario/`: glossários PT→EN e PT→ES em JSON.
- `corpus/definicoes/`: definições e notas jurídicas usadas pelo módulo de RAG.
- `results/`: saídas de tradução (baseline e adaptadas).
- `scripts/`: utilidades (`pipeline.py`, `evaluate_translations.py`).

## Fluxo da Pipeline
1. **Extração HTML**: `pipeline.py` usa BeautifulSoup+lxml para capturar apenas o texto relevante de cada arquivo em `arquivos_juridicos/` e salva em `data/extracted/`.
2. **Segmentação**: o texto é quebrado em blocos curtos para evitar estouro de contexto nos modelos de tradução.
3. **Baseline MT**: os blocos são traduzidos com `facebook/m2m100_418M`, configurando `src_lang=pt` e forçando `forced_bos_token_id` para `en` e `es`.

4. **Adaptação jurídica**:
   - *Glossário*: termos sensíveis recebem anotações no texto de origem (ex.: `sentença (judgment)`), forçando o modelo a escolher a tradução correta.
   - *RAG*: definições relevantes são recuperadas de `corpus/definicoes/` por embeddings (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) e anexadas ao bloco como contexto jurídico.
   - *Pós-processamento*: substituições finais garantem a presença dos termos do glossário na saída.
5. **Comparação**: baseline e versão adaptada são salvas em `results/` para cada idioma.

## Decisões de bibliotecas e por quê
- `beautifulsoup4` + `lxml` (Extração HTML): simples, robustos e rápidos para limpar HTML e ficar só com texto útil.
- `transformers` + modelo `facebook/m2m100_418M` (Tradução): modelo multilingue estável e público, aceita forçar o idioma-alvo via token especial. Funciona bem em CPU (mais lento), sem depender de serviços externos.
- `torch` (Execução do modelo): backend usado pelo `transformers` para carregar pesos e gerar saídas. Versão recente é necessária para os recursos de geração.
- `sentencepiece` (Tokenização): requerido por alguns modelos da família M2M/Marian para preparar texto antes da tradução.
- `sentence-transformers` (Embeddings para RAG): transforma textos (definições jurídicas e blocos) em vetores comparáveis, permitindo recuperar as definições mais parecidas com o conteúdo do bloco.
- `sacrebleu` (Métricas): calcula BLEU/TER de forma reprodutível.

Objetivo geral das escolhas: rodar localmente sem dependência de APIs pagas, com peças amplamente usadas e documentação abundante, preservando a possibilidade de evoluir para GPU ou troca de modelo depois.

## Scripts: o que cada um faz
- `scripts/pipeline.py`
   - Lê HTMLs em `arquivos_juridicos/`, extrai texto e segmenta em blocos.
   - Traduz cada bloco de duas formas:
      - Baseline (sem contexto extra).
      - Adaptada (com anotação de glossário + contexto RAG opcional + pós-processamento de termos).
   - Salva resultados incrementalmente por bloco em `results/` e imprime progresso.
   - Parâmetros úteis: `--languages en,es`, `--max-chars`, `--max-new-tokens`, `--rag`, `--no-glossary`.

- `scripts/evaluate_translations.py`
   - Compara os arquivos `results/<doc>_baseline_<lang>.txt` e `results/<doc>_adapted_<lang>.txt` com uma referência em `data/references/<doc>_<lang>_ref.txt`.
   - Métricas: BLEU, TER e acurácia de termos do glossário.

- `scripts/generate_references.py`
   - Gera “rascunhos de referência” automaticamente a partir de `data/extracted/<doc>.txt` usando o mesmo modelo de tradução.
   - Serve só para acelerar testes: o texto gerado é automático. A ideia é você revisar e corrigir termos/trechos importantes, criando uma referência melhor para as métricas.

## Glossário: propósito e como é usado
Glossário é um dicionário PT→EN/ES para termos jurídicos sensíveis. Objetivo: padronizar e evitar ambiguidades (ex.: “mandado de segurança” → “writ of mandamus”).

Como aplicamos:
- Anotação no texto-fonte: ao detectar o termo, adicionamos a tradução entre parênteses (dica forte ao modelo).
- Pós-processamento na saída: garantimos que os termos apareçam como no glossário quando houver variação.

Arquivos:
- `glossario/glossario_pt_en.json`
- `glossario/glossario_pt_es.json`

Ampliação: adicione entradas no JSON (chave: termo em PT; valor: tradução preferida). Prefira letras minúsculas e termos compostos completos.

## RAG: o que é e como usamos
RAG (Retrieval-Augmented Generation) é “geração aumentada por recuperação de contexto”. Em vez de pedir que o modelo “saiba tudo”, recuperamos pequenos trechos relevantes de um corpus local e anexamos ao bloco antes de traduzir. Isso orienta o modelo a escolher vocabulário/estrutura típicos do domínio jurídico.

Neste projeto:
- Indexamos as definições em `corpus/definicoes/` com embeddings.
- Para cada bloco, buscamos as definições mais próximas (similaridade semântica) e anexamos como “Contexto jurídico”.
- É opcional (`--rag`); útil quando o texto tem termos de arte ou construções ambíguas.

## `corpus/definicoes/`: conteúdo e formato
- Finalidade: pequenos textos com definições/notas jurídicas que ajudam a guiar a tradução.
- Formato: um ou mais arquivos `.txt` com texto corrido. Todos os `.txt` na pasta são carregados.
- Dicas: mantenha entradas curtas e claras, com linguagem definicional. Ex.: “Coisa julgada: ...”

## Fluxo real numa aplicação online (exemplo prático)
Imagine um portal onde você faz upload de N HTMLs e escolhe idiomas (EN/ES). O fluxo seria:

1) Upload e organização
- Front-end envia os arquivos; o back-end salva e enfileira um “job” por documento.

2) Extração e segmentação
- Worker lê HTML, extrai texto limpo (BeautifulSoup+lxml) e segmenta em blocos (tamanho configurável para performance).

3) Tradução baseline e adaptada
- Carrega o modelo de tradução (em memória, reusado entre jobs para velocidade).
- Para cada bloco: traduz baseline; anota o texto com glossário; (opcional) recupera definições via RAG; traduz adaptado; aplica pós-processamento.
- Salva incrementalmente a cada bloco (checkpoint) para permitir retomar em caso de interrupção.

4) Resultado e revisão
- API expõe status e arquivos parciais/finais para download (baseline e adaptado). Um painel permite visualizar lado a lado.
- Referências “boas” podem ser criadas editando a saída adaptada — essas revisões alimentam o glossário/corpus para evoluir a qualidade.

5) Avaliação e melhoria contínua
- Métricas automáticas (BLEU/TER) no servidor, contra referências revisadas.
- Logs simples por bloco (tempo por bloco, tamanho, termos aplicados) para monitorar gargalos e qualidade.

Pontos práticos de engenharia:
- Fila/assíncrono: use um job queue (ex.: Celery/RQ) para escalar o processamento.
- Cache de modelo/embeddings: manter em memória por worker para evitar recarregar.
- Observabilidade: progressos por bloco e checkpoints em disco/objeto (S3/Azure Blob).
- Segurança: higienizar HTMLs, limitar tamanhos e checar conteúdo.
- Custos/desempenho: GPU acelera muito; em CPU, prefira blocos maiores e menos idiomas simultâneos.

## Avaliação Planejada
- **Métricas automáticas**: BLEU e TER via `scripts/evaluate_translations.py` com referência manual (`data/references/<documento>_<idioma>_ref.txt`).
- **Precisão de termos**: verifica quantos termos do glossário aparecem corretamente na tradução.
- **Quadro qualitativo**: tabela com exemplos onde a adaptação evita ambiguidades.

## Como Executar
```powershell
python -m pip install -r requirements.txt
python scripts/pipeline.py --languages en,es --rag
python scripts/pipeline.py --languages en,es --documents InteriorTeor30 --device cuda --no-rag

# Após revisar outputs e gerar referências:

python scripts/evaluate_translations.py <nome_do_html_sem_extensao> en
python scripts/evaluate_translations.py <nome_do_html_sem_extensao> es

#exemplo:
#InteriorTeor30 é o menor
python scripts/evaluate_translations.py InteriorTeor30 en
python scripts/evaluate_translations.py InteriorTeor30 es


```

### Requisitos Principais
- Python 3.10+
- Pacotes: `beautifulsoup4`, `lxml`, `transformers`, `sentence-transformers`, `torch`, `sacrebleu`, `sentencepiece`.

## Roadmap
1. Organizar HTMLs e garantir extração consistente.
2. Curar glossário mínimo (10+ termos críticos) e definições de apoio.
3. Rodar pipeline nos idiomas alvo e revisar qualitativamente.
4. Criar referências humanas para um subconjunto de parágrafos.
5. Calcular métricas e documentar ganhos (gráficos/tabelas simples).
6. Escrever análise crítica e limitações para o relatório do TCC.

## Próximos Passos
- Expandir glossário com validação de especialista.
- Adicionar métricas humanas (avaliação de juristas).
- Investigar fine-tuning leve (LoRA) caso haja corpus paralelo suficiente.
- Preparar apresentação com fluxo visual da pipeline e resultados comparativos.
