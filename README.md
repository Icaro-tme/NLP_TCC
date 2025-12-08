# NLP TCC - Sistema de Tradução Jurídica com Análise Comparativa

Sistema de tradução de documentos jurídicos usando LLM (Google Gemini) com contexto RAG, incluindo comparação com tradução de máquina tradicional (LibreTranslate) e avaliação de qualidade.

## Requisitos de Sistema

- **Python**: 3.10
- **Conda**: Miniconda ou Anaconda (para gerenciamento de ambientes isolados)
- **Hardware**: Intel UHD Graphics (GPU integrada) - compatível com PyTorch CPU

## Instalação do Conda

Se você ainda não tem o Conda instalado:

1. Baixe o [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (versão mais leve) ou [Anaconda](https://www.anaconda.com/download)
2. Execute o instalador seguindo as instruções padrão
3. Reinicie o terminal/PowerShell após a instalação
4. Verifique a instalação: `conda --version`

## Configuração do Ambiente Principal (`tcc_nlp`)

Este ambiente contém toda a aplicação principal: backend FastAPI, RAG com embeddings, avaliação de métricas, e integração com Google Gemini.

### 1. Criar e ativar o ambiente

```powershell
conda create -n tcc_nlp python=3.10 -y
conda activate tcc_nlp
```

### 2. Instalar PyTorch (CPU version para Intel UHD Graphics)

```powershell
pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2
```

### 3. Instalar dependências do projeto

```powershell
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com:

```
# Google Gemini API
GEMINI_API_KEY=sua_chave_aqui

# LibreTranslate (opcional, padrão: http://localhost:5000)
LIBRETRANSLATE_URL=http://localhost:5000
# LIBRETRANSLATE_API_KEY=  # Necessário apenas se usar instância pública
```

Para obter uma chave do Google Gemini: https://ai.google.dev/

### 5. Inicializar banco de dados e índices

```powershell
# Criar diretórios necessários
New-Item -ItemType Directory -Force -Path data/db, data/extracted, data/rag_index, results/text, results/html, results/telemetry

# Executar script de migração (se necessário)
python scripts/migrate_ids.py
```

## Configuração do Ambiente LibreTranslate (`libretranslate_env`)

LibreTranslate requer versões de dependências incompatíveis com o ambiente principal (especialmente `torch==2.4.0` vs `torch==2.1.2`). Por isso, roda em ambiente isolado como servidor HTTP.

### 1. Criar e ativar o ambiente

```powershell
conda create -n libretranslate_env python=3.10 -y
conda activate libretranslate_env
```

### 2. Instalar LibreTranslate

```powershell
pip install libretranslate
```

A instalação inclui ~98 modelos de tradução e pode levar alguns minutos.

### 3. (Opcional) Exportar dependências

```powershell
pip freeze > requirements-libretranslate.txt
```

## Executando o Sistema

O sistema requer dois processos rodando simultaneamente:

### 1. Iniciar o servidor LibreTranslate (Terminal 1)

```powershell
conda activate libretranslate_env
libretranslate --host 0.0.0.0 --port 5000
```

**Aguarde** a mensagem "Running on http://0.0.0.0:5000" antes de prosseguir.

Opções úteis:
- `--load-only pt,en`: Carregar apenas modelos português/inglês (mais rápido)
- `--api-keys`: Habilitar autenticação (produção)
- `--frontend-timeout 60000`: Aumentar timeout para documentos grandes

Documentação completa: https://github.com/LibreTranslate/LibreTranslate

### 2. Iniciar o backend FastAPI (Terminal 2)

```powershell
conda activate tcc_nlp
cd src/api
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

A API estará disponível em `http://localhost:8000` com documentação interativa em `http://localhost:8000/docs`.

### 3. (Opcional) Iniciar o frontend Quasar

Abra um terceiro terminal:

```powershell
cd ..\frontend_repo\interface
npm install  # Apenas na primeira vez
npm run dev
```

A interface web estará disponível em `http://localhost:9000`.

## Troubleshooting

### LibreTranslate não inicia

**Problema**: `ModuleNotFoundError: No module named 'argostranslate'`
**Solução**: Certifique-se de estar no ambiente correto: `conda activate libretranslate_env`

**Problema**: "Port 5000 already in use"
**Solução**: 
```powershell
# Verificar processo na porta 5000
netstat -ano | findstr :5000

# Matar processo (substitua PID)
taskkill /PID <PID> /F

# Ou usar porta alternativa
libretranslate --port 5001
# E atualizar .env: LIBRETRANSLATE_URL=http://localhost:5001
```

### Erros de compatibilidade PyTorch

**Problema**: `RuntimeError: Numpy is not available`
**Solução**: Verifique versões compatíveis:
```powershell
conda activate tcc_nlp
python -c "import torch; print(torch.__version__)"  # Deve ser 2.1.2
python -c "import numpy; print(numpy.__version__)"  # Deve ser 1.24.3
```

Se incorreto, reinstale:
```powershell
pip uninstall torch torchvision torchaudio numpy -y
pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2
pip install numpy==1.24.3
```

### Backend FastAPI retorna 500

**Problema**: `ConnectionError: Could not connect to LibreTranslate`
**Solução**: Verifique se o servidor LibreTranslate está rodando:
```powershell
# Testar manualmente
curl http://localhost:5000/languages
```

Se não responder, inicie conforme seção "Executando o Sistema".

### CUDA errors em sistema com Intel GPU

**Problema**: `torch.cuda.is_available() == False` mas código tenta usar GPU
**Solução**: O sistema usa CPU-only torch por design (Intel UHD Graphics). Verifique `requirements.txt`:
```
torch==2.1.2  # CPU version, NO CUDA
```

Não instale versões CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118` ❌

## Desenvolvimento

### Adicionar nova métrica de avaliação

Edite `src/services/evaluation_service.py`:

```python
def compute_doc(self, documento: str, variante: str, idioma_destino: str):
    # ... código existente ...
    
    # Nova métrica
    chrf = sacrebleu.corpus_chrf([texto_sistema], [[texto_ref]])
    return {
        "bleu": bleu.score / 100,
        "chrf": chrf.score / 100,  # Adicione aqui
        # ...
    }
```

### Testar backend isoladamente

```powershell
conda activate tcc_nlp
pytest tests/  # (se testes existirem)

# Ou teste manual
python -c "from src.backends.libretranslate_backend import LibreTranslateClient; c = LibreTranslateClient(); print(c.translate('Olá mundo'))"
```

## Dependências Principais

### Ambiente `tcc_nlp`
- **FastAPI**: 0.109.0 - Framework web assíncrono
- **PyTorch**: 2.1.2 (CPU) - Deep learning
- **Transformers**: 4.35.2 - Modelos LLM/embeddings
- **Sentence-Transformers**: 2.2.2 - Embeddings semânticos
- **Spacy**: 3.7.2 - NLP/segmentação
- **Google GenerativeAI**: 0.8.5 - API Gemini
- **Sacrebleu**: 2.5.0 - Métricas de tradução

### Ambiente `libretranslate_env`
- **LibreTranslate**: 1.8.3 - Servidor de tradução
- **PyTorch**: 2.4.0 - Requerido por LibreTranslate
- **Argostranslate**: 1.9.6 - Engine de tradução
- **CTranslate2**: 4.6.2 - Inferência rápida

## Licença

Projeto acadêmico desenvolvido para TCC (Trabalho de Conclusão de Curso).

## Referências

- [LibreTranslate GitHub](https://github.com/LibreTranslate/LibreTranslate)
- [Google Gemini API](https://ai.google.dev/)
- [SacreBLEU Paper](https://aclanthology.org/W18-6319/)
- [RAG (Retrieval-Augmented Generation)](https://arxiv.org/abs/2005.11401)
