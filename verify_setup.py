"""
Script de verificação de setup completo.

Verifica se todos os componentes do sistema estão instalados e configurados corretamente:
- Ambientes conda (tcc_nlp, libretranslate_env)
- Dependências Python
- LibreTranslate API (se rodando)
- Variáveis de ambiente
- Estrutura de diretórios
"""

import sys
import os
from pathlib import Path

# Cores ANSI para output colorido
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def check_mark(passed: bool) -> str:
    """Retorna símbolo check/cross baseado no resultado."""
    return f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"

def print_section(title: str):
    """Imprime cabeçalho de seção."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def check_python_version():
    """Verifica versão do Python."""
    version = sys.version_info
    passed = version.major == 3 and version.minor == 10
    status = check_mark(passed)
    print(f"{status} Python {version.major}.{version.minor}.{version.micro}", end="")
    if not passed:
        print(f" {YELLOW}(Recomendado: 3.10.x){RESET}")
    else:
        print()
    return passed

def check_module(module_name: str, expected_version: str = None) -> bool:
    """Verifica se módulo Python está instalado."""
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "desconhecida")
        passed = True
        if expected_version and version != expected_version:
            print(f"{YELLOW}⚠{RESET} {module_name} {version} (esperado: {expected_version})")
            passed = False
        else:
            print(f"{GREEN}✓{RESET} {module_name} {version}")
        return passed
    except ImportError:
        print(f"{RED}✗{RESET} {module_name} {RED}NÃO INSTALADO{RESET}")
        return False

def check_libretranslate_api():
    """Verifica se LibreTranslate está rodando."""
    import requests
    url = os.getenv("LIBRETRANSLATE_URL", "http://localhost:5000")
    try:
        response = requests.get(f"{url}/languages", timeout=5)
        if response.status_code == 200:
            print(f"{GREEN}✓{RESET} LibreTranslate API em {url}")
            return True
        else:
            print(f"{RED}✗{RESET} LibreTranslate respondeu com status {response.status_code}")
            return False
    except requests.RequestException:
        print(f"{RED}✗{RESET} LibreTranslate não está rodando em {url}")
        print(f"   {YELLOW}Inicie com: conda activate libretranslate_env && libretranslate{RESET}")
        return False

def check_env_vars():
    """Verifica variáveis de ambiente."""
    required = ["GEMINI_API_KEY"]
    optional = ["LIBRETRANSLATE_URL", "LIBRETRANSLATE_API_KEY"]
    
    all_ok = True
    for var in required:
        value = os.getenv(var)
        if value and value != f"your_{var.lower()}_here":
            print(f"{GREEN}✓{RESET} {var} configurada")
        else:
            print(f"{RED}✗{RESET} {var} {RED}NÃO CONFIGURADA{RESET}")
            print(f"   {YELLOW}Crie arquivo .env na raiz com: {var}=sua_chave{RESET}")
            all_ok = False
    
    for var in optional:
        value = os.getenv(var)
        if value:
            print(f"{GREEN}✓{RESET} {var} = {value}")
        else:
            print(f"{YELLOW}⚠{RESET} {var} (opcional, usando padrão)")
    
    return all_ok

def check_directories():
    """Verifica estrutura de diretórios."""
    dirs = [
        "data/db",
        "data/extracted",
        "data/rag_index",
        "results/text",
        "results/html",
        "results/telemetry",
        "arquivos_juridicos",
        "corpus"
    ]
    
    all_ok = True
    for dir_path in dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"{GREEN}✓{RESET} {dir_path}/")
        else:
            print(f"{RED}✗{RESET} {dir_path}/ {YELLOW}(será criado automaticamente){RESET}")
            all_ok = False
    
    return all_ok

def check_files():
    """Verifica arquivos críticos."""
    files = [
        ("requirements.txt", True),
        ("requirements-libretranslate.txt", True),
        (".env", False),
        (".env.example", True),
        ("src/backends/libretranslate_backend.py", True),
        ("src/api/app.py", True)
    ]
    
    all_ok = True
    for file_path, required in files:
        path = Path(file_path)
        if path.exists():
            print(f"{GREEN}✓{RESET} {file_path}")
        elif required:
            print(f"{RED}✗{RESET} {file_path} {RED}FALTANDO{RESET}")
            all_ok = False
        else:
            print(f"{YELLOW}⚠{RESET} {file_path} (opcional, mas recomendado)")
    
    return all_ok

def main():
    """Executa todas as verificações."""
    print(f"\n{BLUE}{'*'*60}{RESET}")
    print(f"{BLUE}*  Verificação de Setup - TCC NLP Tradução Jurídica  *{RESET}")
    print(f"{BLUE}{'*'*60}{RESET}")
    
    results = {}
    
    # Python
    print_section("1. Versão Python")
    results['python'] = check_python_version()
    
    # Dependências principais
    print_section("2. Dependências Principais (tcc_nlp)")
    modules = [
        ("torch", "2.1.2"),
        ("numpy", "1.24.3"),
        ("transformers", "4.35.2"),
        ("sentence_transformers", "2.2.2"),
        ("fastapi", None),
        ("spacy", "3.7.2"),
        ("sacrebleu", None),
        ("google.generativeai", None),
        ("bs4", None),
        ("requests", None)
    ]
    results['dependencies'] = all(check_module(name, ver) for name, ver in modules)
    
    # LibreTranslate API
    print_section("3. LibreTranslate API")
    results['libretranslate'] = check_libretranslate_api()
    
    # Variáveis de ambiente
    print_section("4. Variáveis de Ambiente")
    results['env_vars'] = check_env_vars()
    
    # Estrutura de diretórios
    print_section("5. Estrutura de Diretórios")
    results['directories'] = check_directories()
    
    # Arquivos críticos
    print_section("6. Arquivos Críticos")
    results['files'] = check_files()
    
    # Resumo final
    print_section("RESUMO")
    total = len(results)
    passed = sum(results.values())
    percentage = (passed / total) * 100
    
    print(f"\nVerificações: {passed}/{total} ({percentage:.0f}%)")
    
    if percentage == 100:
        print(f"\n{GREEN}✓ TUDO CONFIGURADO CORRETAMENTE!{RESET}")
        print(f"\n{BLUE}Próximos passos:{RESET}")
        print(f"  1. Terminal 1: conda activate libretranslate_env && libretranslate")
        print(f"  2. Terminal 2: conda activate tcc_nlp && cd src/api && uvicorn app:app --reload")
        print(f"  3. Acesse: http://localhost:8000/docs")
    elif percentage >= 70:
        print(f"\n{YELLOW}⚠ QUASE PRONTO - Corrija os itens marcados com ✗{RESET}")
    else:
        print(f"\n{RED}✗ SETUP INCOMPLETO - Revise a documentação (README.md){RESET}")
    
    print(f"\n{BLUE}{'*'*60}{RESET}\n")
    return 0 if percentage == 100 else 1

if __name__ == "__main__":
    # Carregar .env se existir
    env_path = Path(".env")
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv()
    
    sys.exit(main())
