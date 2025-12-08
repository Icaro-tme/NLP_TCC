# Comandos Úteis - TCC NLP

## Gerenciamento de Ambientes Conda

### Listar ambientes
```powershell
conda env list
```

### Ativar ambiente principal
```powershell
conda activate tcc_nlp
```

### Ativar ambiente LibreTranslate
```powershell
conda activate libretranslate_env
```

### Desativar ambiente atual
```powershell
conda deactivate
```

### Remover ambiente (caso precise recriar)
```powershell
conda env remove -n tcc_nlp
conda env remove -n libretranslate_env
```

### Exportar ambiente (backup)
```powershell
conda activate tcc_nlp
conda env export > environment.yml
```

## Inicialização do Sistema

### 1. LibreTranslate (Terminal 1)
```powershell
# Básico
conda activate libretranslate_env
libretranslate

# Apenas PT/EN (mais rápido)
libretranslate --load-only pt,en

# Porta customizada
libretranslate --port 5001

# Com autenticação
libretranslate --api-keys --api-keys-db-path keys.db
```

### 2. Backend FastAPI (Terminal 2)
```powershell
# Desenvolvimento (auto-reload)
conda activate tcc_nlp
cd src/api
uvicorn app:app --reload --port 8000

# Produção
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4

# Com HTTPS
uvicorn app:app --ssl-keyfile key.pem --ssl-certfile cert.pem
```

### 3. Frontend Quasar (Terminal 3)
```powershell
cd frontend_repo/interface

# Desenvolvimento
npm run dev

# Build produção
npm run build

# Servir build
npm run serve
```

## Testes e Verificação

### Verificar setup completo
```powershell
conda activate tcc_nlp
python verify_setup.py
```

### Testar LibreTranslate
```powershell
# Via curl (PowerShell)
Invoke-WebRequest http://localhost:5000/languages

# Via Python
python -c "from src.backends.libretranslate_backend import LibreTranslateClient; print(LibreTranslateClient().translate('Olá'))"
```

### Testar backend FastAPI
```powershell
# Health check
curl http://localhost:8000/health

# Documentação interativa
start http://localhost:8000/docs

# Testar endpoint
curl -X POST http://localhost:8000/traduzir_crua `
  -H "Content-Type: application/json" `
  -d '{"documento":"test.html","idioma_destino":"en"}'
```

## Desenvolvimento

### Instalar nova dependência
```powershell
conda activate tcc_nlp
pip install nome_do_pacote
pip freeze > requirements.txt  # Atualizar requirements
```

### Executar script Python
```powershell
conda activate tcc_nlp
python scripts/mvp_cli.py
```

### Acessar console Python com contexto
```powershell
conda activate tcc_nlp
python
>>> from src.backends.libretranslate_backend import LibreTranslateClient
>>> client = LibreTranslateClient()
>>> client.translate("teste")
```

### Formatar código
```powershell
# Instalar ferramentas (uma vez)
pip install black isort flake8

# Formatar
black src/
isort src/
flake8 src/
```

## Banco de Dados

### Criar tabelas
```powershell
conda activate tcc_nlp
python -c "from src.persistence import create_tables; create_tables()"
```

### Backup
```powershell
# SQLite
Copy-Item data\db\tcc.db data\db\tcc_backup_$(Get-Date -Format 'yyyyMMdd').db
```

### Reset (cuidado!)
```powershell
Remove-Item data\db\tcc.db
python scripts/migrate_ids.py
```

## RAG e Embeddings

### Recriar índice FAISS
```powershell
conda activate tcc_nlp
python -c "from src.rag import rebuild_index; rebuild_index()"
```

### Limpar cache
```powershell
Remove-Item -Recurse -Force data\rag_index\*
```

## Processamento de Documentos

### Indexar HTML
```powershell
conda activate tcc_nlp
python -c "from src.dom_indexer import indexar_html; indexar_html('arquivos_juridicos/documento.html')"
```

### Traduzir documento
```powershell
# Via script
python scripts/mvp_cli.py traduzir documento.html --variante adapted

# Via API
curl -X POST http://localhost:8000/traduzir `
  -H "Content-Type: application/json" `
  -d '{"documento":"documento.html","variante":"adapted","idioma_destino":"en"}'
```

### Avaliar tradução
```powershell
curl -X POST http://localhost:8000/avaliar `
  -H "Content-Type: application/json" `
  -d '{"documento":"documento","variante":"crua","idioma_destino":"en"}'
```

## Limpeza e Manutenção

### Limpar cache pip
```powershell
pip cache purge
```

### Limpar arquivos temporários Python
```powershell
Get-ChildItem -Path . -Include __pycache__,*.pyc -Recurse -Force | Remove-Item -Force -Recurse
```

### Limpar resultados antigos
```powershell
Remove-Item results\html\* -Force
Remove-Item results\text\* -Force
```

### Verificar espaço em disco
```powershell
# Tamanho dos ambientes conda
Get-ChildItem C:\Users\conta\anaconda3\envs -Directory | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
    [PSCustomObject]@{
        Name = $_.Name
        SizeGB = [math]::Round($size, 2)
    }
}
```

## Debug e Logging

### Habilitar logs detalhados FastAPI
```powershell
$env:LOG_LEVEL="DEBUG"
uvicorn app:app --reload --log-level debug
```

### Ver logs LibreTranslate
```powershell
# LibreTranslate já loga no stdout
# Para salvar em arquivo:
libretranslate 2>&1 | Tee-Object -FilePath logs\libretranslate.log
```

### Monitorar requests HTTP
```powershell
# No Python (adicionar ao código)
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Performance

### Benchmark tradução
```powershell
conda activate tcc_nlp
Measure-Command {
    python -c "from src.backends.libretranslate_backend import LibreTranslateClient; LibreTranslateClient().translate('teste' * 100)"
}
```

### Monitorar uso de memória
```powershell
# Durante execução do backend
Get-Process python | Select-Object ProcessName, @{Name="MemMB";Expression={[math]::Round($_.WorkingSet / 1MB, 2)}}
```

## Git (se versionado)

### Ignorar arquivos grandes
```bash
# .gitignore
data/rag_index/
*.db
*.pyc
__pycache__/
.env
node_modules/
dist/
```

### Commit típico
```bash
git add .
git commit -m "feat: adiciona tradução crua com LibreTranslate"
git push origin main
```

## Troubleshooting Rápido

### Porta 5000 ocupada
```powershell
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### Porta 8000 ocupada
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Reinstalar dependências corrompidas
```powershell
conda activate tcc_nlp
pip install --force-reinstall --no-cache-dir torch==2.1.2
```

### Reset completo (último recurso)
```powershell
# Backup dados importantes!
conda env remove -n tcc_nlp
conda env remove -n libretranslate_env

# Recriar seguindo README.md
conda create -n tcc_nlp python=3.10 -y
# ... resto do setup
```

## Atalhos Úteis (Criar aliases)

Adicione ao seu `$PROFILE` (PowerShell):
```powershell
# Abrir profile: notepad $PROFILE

function Start-TCC-LibreTranslate {
    conda activate libretranslate_env
    libretranslate --load-only pt,en
}

function Start-TCC-Backend {
    conda activate tcc_nlp
    Set-Location "C:\Users\conta\Desktop\Nova pasta\NLP_TCC\src\api"
    uvicorn app:app --reload
}

function Test-TCC-Setup {
    conda activate tcc_nlp
    Set-Location "C:\Users\conta\Desktop\Nova pasta\NLP_TCC"
    python verify_setup.py
}

# Usar:
# Start-TCC-LibreTranslate
# Start-TCC-Backend
# Test-TCC-Setup
```

## Recursos Externos

- **LibreTranslate Docs**: https://libretranslate.com/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Quasar Docs**: https://quasar.dev/
- **Conda Cheatsheet**: https://docs.conda.io/projects/conda/en/latest/user-guide/cheatsheet.html
- **PyTorch Docs**: https://pytorch.org/docs/stable/index.html
