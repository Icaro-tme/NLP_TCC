"""Script para carregar dados manuais em lote (bulk insert) no banco de dados.

Lê arquivos TSV em:
- glossario/manual_entries.txt (glossário)
- corpus/manual_notes.txt (corpus)

E insere no banco de dados SQLite.

Uso:
    python scripts/load_manual_data.py [--clear]
    
Opções:
    --clear: Limpa as tabelas antes de inserir (default: apenas adiciona)

"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'db' / 'nlp_tcc.sqlite'
# Arquivos validados contra tradução humana
GLOSSARY_FILES = [
    PROJECT_ROOT / 'glossario' / 'glossario_validado_humano.txt',
]
CORPUS_FILES = [
    PROJECT_ROOT / 'corpus' / 'corpus_validado_humano.txt',
]

def load_glossary_file(conn: sqlite3.Connection, file_path: Path) -> tuple[int, int]:
    """Carrega entradas de um arquivo TSV de glossário. Retorna (inseridas, ignoradas)."""
    if not file_path.exists():
        print(f"[AVISO] Arquivo não encontrado: {file_path}")
        return (0, 0)
    
    print(f"[glossary_entries] Lendo {file_path.name}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Primeira linha é cabeçalho: term_src|lang_src|term_tgt|lang_tgt|notes
    header = lines[0].strip()
    if not header.startswith('term_src'):
        print(f"[ERRO] Cabeçalho inesperado em {file_path.name}: {header}")
        return (0, 0)
    
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        parts = line.split('|')
        if len(parts) < 4:
            print(f"[AVISO] {file_path.name} linha {i} ignorada (formato inválido): {line[:50]}...")
            skipped += 1
            continue
        
        term_src = parts[0].strip()
        lang_src = parts[1].strip()
        term_tgt = parts[2].strip()
        lang_tgt = parts[3].strip()
        notes = parts[4].strip() if len(parts) > 4 else None
        
        # Verificar duplicatas
        cur.execute(
            """SELECT COUNT(*) FROM glossary_entries 
               WHERE term_src = ? AND lang_src = ? AND term_tgt = ? AND lang_tgt = ?""",
            (term_src, lang_src, term_tgt, lang_tgt)
        )
        if cur.fetchone()[0] > 0:
            skipped += 1
            continue
        
        try:
            cur.execute(
                """INSERT INTO glossary_entries (term_src, lang_src, term_tgt, lang_tgt, notes) 
                   VALUES (?, ?, ?, ?, ?)""",
                (term_src, lang_src, term_tgt, lang_tgt, notes)
            )
            inserted += 1
        except Exception as e:
            print(f"[ERRO] {file_path.name} linha {i}: {e}")
            skipped += 1
    
    return (inserted, skipped)

def load_glossary(conn: sqlite3.Connection, clear: bool = False) -> int:
    """Carrega entradas do glossário de múltiplos arquivos TSV."""
    cur = conn.cursor()
    
    if clear:
        print("[glossary_entries] Limpando tabela...")
        cur.execute("DELETE FROM glossary_entries")
        conn.commit()
    
    total_inserted = 0
    total_skipped = 0
    
    for file_path in GLOSSARY_FILES:
        inserted, skipped = load_glossary_file(conn, file_path)
        total_inserted += inserted
        total_skipped += skipped
    
    conn.commit()
    print(f"[glossary_entries] TOTAL: {total_inserted} inseridas | {total_skipped} ignoradas")
    return total_inserted


def load_corpus(conn: sqlite3.Connection, clear: bool = False) -> int:
    """Carrega snippets do corpus do arquivo TSV."""
    if not CORPUS_FILE.exists():
        print(f"[AVISO] Arquivo não encontrado: {CORPUS_FILE}")
        return 0
    
    cur = conn.cursor()
    
    if clear:
        print("[corpus_snippets] Limpando tabela...")
        cur.execute("DELETE FROM corpus_snippets")
        conn.commit()
    
    print(f"[corpus_snippets] Lendo {CORPUS_FILE}...")
    with open(CORPUS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Primeira linha é cabeçalho: text|language|tags|notes
    header = lines[0].strip()
    if not header.startswith('text'):
        print(f"[ERRO] Cabeçalho inesperado: {header}")
        return 0
    
    inserted = 0
    skipped = 0
    
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        parts = line.split('|')
        if len(parts) < 3:
            print(f"[AVISO] Linha {i} ignorada (formato inválido): {line[:50]}...")
            skipped += 1
            continue
        
        text = parts[0].strip()
        language = parts[1].strip()
        tags = parts[2].strip() if len(parts) > 2 else None
        notes = parts[3].strip() if len(parts) > 3 else None
        
        # Verificar duplicatas exatas
        cur.execute(
            """SELECT COUNT(*) FROM corpus_snippets 
               WHERE text = ? AND language = ?""",
            (text, language)
        )
def load_corpus_file(conn: sqlite3.Connection, file_path: Path) -> tuple[int, int]:
    """Carrega snippets de um arquivo TSV de corpus. Retorna (inseridos, ignorados)."""
    if not file_path.exists():
        print(f"[AVISO] Arquivo não encontrado: {file_path}")
        return (0, 0)
    
    print(f"[corpus_snippets] Lendo {file_path.name}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Primeira linha é cabeçalho: text|language|tags|notes
    header = lines[0].strip()
    if not header.startswith('text'):
        print(f"[ERRO] Cabeçalho inesperado em {file_path.name}: {header}")
        return (0, 0)
    
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        
        parts = line.split('|')
        if len(parts) < 3:
            print(f"[AVISO] {file_path.name} linha {i} ignorada (formato inválido): {line[:50]}...")
            skipped += 1
            continue
        
        text = parts[0].strip()
        language = parts[1].strip()
        tags = parts[2].strip() if len(parts) > 2 else None
        notes = parts[3].strip() if len(parts) > 3 else None
        
        # Verificar duplicatas exatas
        cur.execute(
            """SELECT COUNT(*) FROM corpus_snippets 
               WHERE text = ? AND language = ?""",
            (text, language)
        )
        if cur.fetchone()[0] > 0:
            skipped += 1
            continue
        
        try:
            cur.execute(
                """INSERT INTO corpus_snippets (text, language, tags, notes) 
                   VALUES (?, ?, ?, ?)""",
                (text, language, tags, notes)
            )
            inserted += 1
        except Exception as e:
            print(f"[ERRO] {file_path.name} linha {i}: {e}")
            skipped += 1
    
    return (inserted, skipped)

def load_corpus(conn: sqlite3.Connection, clear: bool = False) -> int:
    """Carrega snippets do corpus de múltiplos arquivos TSV."""
    cur = conn.cursor()
    
    if clear:
        print("[corpus_snippets] Limpando tabela...")
        cur.execute("DELETE FROM corpus_snippets")
        conn.commit()
    
    total_inserted = 0
    total_skipped = 0
    
    for file_path in CORPUS_FILES:
        inserted, skipped = load_corpus_file(conn, file_path)
        total_inserted += inserted
        total_skipped += skipped
    
    conn.commit()
    print(f"[corpus_snippets] TOTAL: {total_inserted} inseridos | {total_skipped} ignorados")
    return total_inserted