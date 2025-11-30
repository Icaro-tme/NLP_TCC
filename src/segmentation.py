"""Utilitários de segmentação e janela de contexto.

Atualizações:
- Mantido `naive_sentence_split` (pontuação .?!).
- Adicionada segmentação opcional via spaCy (`spacy_sentence_split`) para evitar cortes de frases.
- Função unificada `get_sentence_segments` escolhe spaCy se disponível, caso contrário fallback para ingênua.

Objetivo: suportar chunking em `TranslationGateway` sem quebrar tokens ou sentido sintático em nós/janelas longas.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple, Literal

import spacy

_SPACY_MODEL_CACHE = {}
_SPACY_DEFAULTS = {
    "pt": "pt_core_news_sm",
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
}

SENTENCE_END = {".", "?", "!"}


def naive_sentence_split(text: str) -> List[str]:
    """Very lightweight sentence splitter (placeholder for nltk/spacy)."""
    parts: List[str] = []
    buff: List[str] = []
    for ch in text:
        buff.append(ch)
        if ch in SENTENCE_END:
            parts.append("".join(buff).strip())
            buff = []
    if buff:
        tail = "".join(buff).strip()
        if tail:
            parts.append(tail)
    return parts


def spacy_sentence_split(text: str, lang: str = "pt") -> List[str]:
    """Segmentação robusta via spaCy (se modelo disponível).

    - Usa limites de sentença do pipeline spaCy.
    - Filtra sentenças vazias.
    - Fallback para lista vazia se spaCy indisponível ou erro.
    """
    if spacy is None:
        return []
    model_name = _SPACY_DEFAULTS.get(lang, _SPACY_DEFAULTS["pt"])
    if model_name not in _SPACY_MODEL_CACHE:
        try:
            _SPACY_MODEL_CACHE[model_name] = spacy.load(model_name)
        except Exception:
            _SPACY_MODEL_CACHE[model_name] = None
    nlp = _SPACY_MODEL_CACHE.get(model_name)
    if nlp is None:
        return []
    try:
        doc = nlp(text)
        return [s.text.strip() for s in doc.sents if s.text.strip()]
    except Exception:
        return []


def get_sentence_segments(
    text: str,
    *,
    lang: str = "pt",
    require_spacy: bool = False,
) -> Tuple[List[str], Literal["spacy", "naive", "single"]]:
    """Retorna sentenças e o método utilizado.

    - Quando `require_spacy=True`, lança erro se spaCy não estiver disponível ou não houver sentenças extraídas.
    - Caso contrário, tenta spaCy, depois cai para a segmentação ingênua e, por último, devolve o texto inteiro.
    """
    if not text.strip():
        return [], "single"
    if require_spacy:
        seg = spacy_sentence_split(text, lang=lang)
        if not seg:
            reason = "spaCy indisponível ou modelo não carregado" if spacy is None else "modelo de linguagem sem sentenças detectadas"
            raise RuntimeError(
                f"Segmentação obrigatória via spaCy falhou: {reason}. "
                f"Instale o pacote e o modelo com: python -m spacy download {_SPACY_DEFAULTS.get(lang, 'pt_core_news_sm')}"
            )
        return seg, "spacy"
    # Caminho permissivo (não obrigatório)
    seg = spacy_sentence_split(text, lang=lang)
    if seg:
        return seg, "spacy"
    seg = naive_sentence_split(text)
    if seg:
        return seg, "naive"
    return [text], "single"


def build_windows(nodes: Iterable[dict], max_chars: int = 800) -> List[Tuple[List[dict], str]]:
    """Group consecutive nodes into context windows respecting a char budget.

    Returns list of tuples: (list_of_nodes, concatenated_text_with_markers)
    """
    windows: List[Tuple[List[dict], str]] = []
    current_nodes: List[dict] = []
    current_text: List[str] = []
    current_len = 0
    for node in nodes:
        text = node.get("original_text", "")
        # Marker ensures we can split later.
        marker = f"<<<NODE:{node['id']}>>>"  # requires node has 'id'
        chunk = marker + "\n" + text + "\n"
        if current_len + len(chunk) > max_chars and current_nodes:
            windows.append((current_nodes[:], "".join(current_text)))
            current_nodes.clear()
            current_text.clear()
            current_len = 0
        current_nodes.append(node)
        current_text.append(chunk)
        current_len += len(chunk)
    if current_nodes:
        windows.append((current_nodes, "".join(current_text)))
    return windows


def split_window_translation(window_text: str) -> List[Tuple[str, str]]:
    """Split translated window back into (node_id, translated_text).

    Relies on marker lines surviving mostly intact; trims surrounding whitespace.
    """
    lines = window_text.splitlines()
    results: List[Tuple[str, str]] = []
    current_id: str | None = None
    buff: List[str] = []
    for line in lines:
        if line.startswith("<<<NODE:") and line.endswith(">>>"):
            # flush previous
            if current_id is not None:
                results.append((current_id, "\n".join(buff).strip()))
            current_id = line[len("<<<NODE:") : -3]
            buff = []
        else:
            buff.append(line)
    if current_id is not None:
        results.append((current_id, "\n".join(buff).strip()))
    return results
