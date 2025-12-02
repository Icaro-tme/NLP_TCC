"""Script de migração para adicionar coluna 'id' às tabelas legadas sem PK explícita.

Tabelas alvo: glossary_entries, corpus_snippets.
Somente recria a tabela se a coluna 'id' NÃO existir.
Preserva dados existentes. Usa BEGIN/COMMIT para atomicidade simples.

Uso:
    python scripts/migrate_ids.py

"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path('data/db/nlp_tcc.sqlite')
print(f"[migração] Usando banco: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def has_id(table: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == 'id' for row in cur.fetchall())

def migrate_glossary():
    if has_id('glossary_entries'):
        print('[glossary_entries] Já possui coluna id. Pulando.')
        return
    print('[glossary_entries] Migrando para adicionar id...')
    cur.execute('SELECT term_src, lang_src, term_tgt, lang_tgt, notes FROM glossary_entries')
    rows = cur.fetchall()
    cur.executescript('''BEGIN;CREATE TABLE glossary_entries_new (id INTEGER PRIMARY KEY, term_src TEXT NOT NULL, lang_src TEXT NOT NULL, term_tgt TEXT NOT NULL, lang_tgt TEXT NOT NULL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
    for term_src, lang_src, term_tgt, lang_tgt, notes in rows:
        term_src = term_src or '(vazio)'
        lang_src = lang_src or 'pt'
        term_tgt = term_tgt or '(blank)'
        lang_tgt = lang_tgt or 'en'
        cur.execute('INSERT INTO glossary_entries_new (term_src, lang_src, term_tgt, lang_tgt, notes) VALUES (?,?,?,?,?)', (term_src, lang_src, term_tgt, lang_tgt, notes))
    cur.executescript('''DROP TABLE glossary_entries;ALTER TABLE glossary_entries_new RENAME TO glossary_entries;COMMIT;''')
    print(f'[glossary_entries] Migrada. Linhas: {len(rows)}')

def migrate_corpus():
    if has_id('corpus_snippets'):
        print('[corpus_snippets] Já possui coluna id. Pulando.')
        return
    print('[corpus_snippets] Migrando para adicionar id...')
    cur.execute('SELECT text, language, tags, notes FROM corpus_snippets')
    rows = cur.fetchall()
    cur.executescript('''BEGIN;CREATE TABLE corpus_snippets_new (id INTEGER PRIMARY KEY, text TEXT NOT NULL, language TEXT NOT NULL, tags TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
    for text, language, tags, notes in rows:
        text = text or ''
        language = language or 'pt'
        cur.execute('INSERT INTO corpus_snippets_new (text, language, tags, notes) VALUES (?,?,?,?)', (text, language, tags, notes))
    cur.executescript('''DROP TABLE corpus_snippets;ALTER TABLE corpus_snippets_new RENAME TO corpus_snippets;COMMIT;''')
    print(f'[corpus_snippets] Migrada. Linhas: {len(rows)}')

migrate_glossary()
migrate_corpus()

print('\n[resultado] Schemas finais:')
for table in ['glossary_entries','corpus_snippets']:
    cur.execute(f'PRAGMA table_info({table})')
    cols = [c[1] for c in cur.fetchall()]
    print(f' - {table}: {cols}')

conn.close()
print('[migração] Concluída.')
