"""Serviço de avaliação de qualidade de tradução comparando variante do sistema com tradução humana.

Métricas implementadas:
- BLEU (sacrebleu)
- chrF (sacrebleu)
- TER (sacrebleu)
- Jaccard médio entre conjuntos de tokens por nó
- Similaridade sintática aproximada (POS tag match rate) via spaCy (opcional)

Fluxo:
1. Extração dos textos humanos por nó a partir de HTML (elementos com data-node-id).
2. Alinhamento com traduções persistidas (baseline/adapted) por node_id usando NodeRepository.
3. Cálculo das métricas agregadas e por nó.

Observação: para similaridade sintática é tentada carga do modelo 'en_core_web_sm' ou
o idioma alvo correspondente; caso não disponível, a métrica é omitida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup

from ..persistence.repos import DocumentRepository, NodeRepository
from ..persistence.db import Database
from ..core.config import PathsConfig

import re
import math

@dataclass
class EvaluationResult:
    documento: str
    idioma: str
    variante: str
    total_nos: int
    bleu: float | None
    chrf: float | None
    ter: float | None
    jaccard_medio: float | None
    pos_accuracy_media: float | None
    sintaxe_habilitada: bool
    por_no: List[Dict[str, object]]
    fallback_alinhamento: bool
    diagnostico: str | None


class EvaluationService:
    def __init__(self, paths: PathsConfig) -> None:
        self.paths = paths
        self.db = Database(paths.db_path)
        self.doc_repo = DocumentRepository(self.db)
        self.node_repo = NodeRepository(self.db)

    # ---------------- Extração HTML Humano -----------------
    @staticmethod
    def extract_human_nodes(html: str) -> Dict[str, str]:
        """Extrai mapa node_path -> texto traduzido humano.

        Assume que o HTML humano foi baseado em variante exportada que preserva
        atributos data-node-id em elementos estruturais.
        """
        soup = BeautifulSoup(html, 'html.parser')
        mapping: Dict[str, str] = {}
        for el in soup.find_all(attrs={'data-node-id': True}):
            node_path = el.get('data-node-id')
            if not node_path:
                continue
            text = el.get_text('\n').strip()
            if text:
                mapping[node_path] = re.sub(r"\s+", " ", text)
        return mapping

    # ---------------- Métricas -----------------
    @staticmethod
    def jaccard(a: str, b: str) -> float:
        ta = set(t for t in a.lower().split() if t)
        tb = set(t for t in b.lower().split() if t)
        if not ta and not tb:
            return 1.0
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        union = len(ta | tb)
        return inter / union if union else 0.0

    @staticmethod
    def pos_match_ratio(sys_text: str, human_text: str, nlp) -> float | None:
        if not sys_text.strip() or not human_text.strip():
            return None
        try:
            doc_sys = nlp(sys_text)
            doc_h = nlp(human_text)
        except Exception:
            return None
        tags_sys = [t.pos_ for t in doc_sys if not t.is_space]
        tags_h = [t.pos_ for t in doc_h if not t.is_space]
        if not tags_sys or not tags_h:
            return None
        # align by min length
        m = min(len(tags_sys), len(tags_h))
        if m == 0:
            return None
        matches = sum(1 for i in range(m) if tags_sys[i] == tags_h[i])
        return matches / m

    def compute(self, documento: str, source_lang: str, target_lang: str, variante: str, human_html: str, usar_fallback: bool = True) -> EvaluationResult:
        document_id = self.doc_repo.find_document_id(documento, source_lang, target_lang)
        if document_id is None:
            raise ValueError(f"Documento não encontrado para {documento} {source_lang}->{target_lang}")
        nodes = self.node_repo.list_nodes(document_id)
        human_map = self.extract_human_nodes(human_html)
        refs: List[str] = []
        hyps: List[str] = []
        per_node: List[Dict[str, object]] = []
        jaccards: List[float] = []
        pos_accs: List[float] = []
        # spaCy opcional
        nlp = None
        sintaxe_habilitada = False
        try:
            import spacy
            model_name = 'en_core_web_sm' if target_lang == 'en' else f'{target_lang}_core_news_sm'
            nlp = spacy.load(model_name)
            sintaxe_habilitada = True
        except Exception:
            nlp = None
            sintaxe_habilitada = False

        # Primeiro tentamos correspondência por data-node-id
        matched_count = 0
        for n in nodes:
            node_path = n.get('node_path')
            human_txt = human_map.get(node_path, '').strip()
            sys_txt = ''
            if variante == 'baseline':
                sys_txt = n.get('baseline_text') or ''
            elif variante == 'adapted':
                sys_txt = n.get('adapted_text') or n.get('translation_text') or n.get('baseline_text') or ''
            human_norm = re.sub(r"\s+", " ", human_txt)
            sys_norm = re.sub(r"\s+", " ", sys_txt)
            if human_norm:
                matched_count += 1
                refs.append(human_norm)
                hyps.append(sys_norm)
                jac = self.jaccard(sys_norm, human_norm)
                jaccards.append(jac)
                pos_ratio = self.pos_match_ratio(sys_norm, human_norm, nlp) if nlp else None
                if pos_ratio is not None:
                    pos_accs.append(pos_ratio)
                per_node.append({
                    'node_id': n.get('id'),
                    'node_path': node_path,
                    'human_len': len(human_norm),
                    'system_len': len(sys_norm),
                    'jaccard': jac,
                    'pos_accuracy': pos_ratio,
                })

        fallback_used = False
        diagnostico: str | None = None
        # Se não houve nenhum match por data-node-id e fallback habilitado, alinhar sequencialmente.
        if matched_count == 0 and usar_fallback:
            fallback_used = True
            diagnostico = (
                "Nenhum nó humano foi associado via data-node-id. Fallback sequencial aplicado. "
                "Para avaliação precisa, gere o HTML humano a partir de uma variante exportada para preservar atributos data-node-id."
            )
            # Extrai blocos de texto humanos sem depender de data-node-id
            soup = BeautifulSoup(human_html, 'html.parser')
            human_blocks: List[str] = []
            for el in soup.find_all(['p','div','span','li']):
                txt = el.get_text(' ').strip()
                if len(txt) >= 3:
                    human_blocks.append(re.sub(r"\s+", " ", txt))
            # Obtém textos do sistema na ordem original dos nós
            system_blocks: List[str] = []
            for n in nodes:
                if variante == 'baseline':
                    system_blocks.append(re.sub(r"\s+", " ", (n.get('baseline_text') or '')))
                else:
                    system_blocks.append(re.sub(r"\s+", " ", (n.get('adapted_text') or n.get('translation_text') or n.get('baseline_text') or '')))
            limit = min(len(human_blocks), len(system_blocks))
            for idx in range(limit):
                htxt = human_blocks[idx]
                stxt = system_blocks[idx]
                if not htxt:
                    continue
                refs.append(htxt)
                hyps.append(stxt)
                jac = self.jaccard(stxt, htxt)
                jaccards.append(jac)
                pos_ratio = self.pos_match_ratio(stxt, htxt, nlp) if nlp else None
                if pos_ratio is not None:
                    pos_accs.append(pos_ratio)
                per_node.append({
                    'node_id': idx,
                    'node_path': f"fallback_seq_{idx}",
                    'human_len': len(htxt),
                    'system_len': len(stxt),
                    'jaccard': jac,
                    'pos_accuracy': pos_ratio,
                })

        bleu = chrf = ter = None
        if refs and hyps:
            try:
                from sacrebleu import corpus_bleu, corpus_chrf, corpus_ter
                bleu = float(corpus_bleu(hyps, [refs]).score)
                chrf = float(corpus_chrf(hyps, [refs]).score)
                ter = float(corpus_ter(hyps, [refs]).score)
            except Exception:
                pass
        jaccard_medio = sum(jaccards)/len(jaccards) if jaccards else None
        pos_media = sum(pos_accs)/len(pos_accs) if pos_accs else None
        return EvaluationResult(
            documento=documento,
            idioma=target_lang,
            variante=variante,
            total_nos=len(per_node),
            bleu=bleu,
            chrf=chrf,
            ter=ter,
            jaccard_medio=jaccard_medio,
            pos_accuracy_media=pos_media,
            sintaxe_habilitada=sintaxe_habilitada,
            por_no=per_node,
            fallback_alinhamento=fallback_used,
            diagnostico=diagnostico,
        )

    # ---------------- Avaliação por Documento (texto integral) -----------------
    def compute_doc(self, documento: str, source_lang: str, target_lang: str, variante: str, human_html: str):
        """Avalia métricas globais comparando texto integral humano vs texto integral da variante do sistema.

        Não realiza alinhamento por nó. Extrai texto humano do HTML e texto do sistema
        decodificando placeholders e concatenando nós na ordem lógica.
        """
        document_id = self.doc_repo.find_document_id(documento, source_lang, target_lang)
        if document_id is None:
            raise ValueError(f"Documento não encontrado para {documento} {source_lang}->{target_lang}")
        nodes = self.node_repo.list_nodes(document_id)
        # Texto do sistema via concatenação de nós com decodificação de placeholders
        try:
            from .text_export_service import TextExportService
        except Exception:
            TextExportService = None  # type: ignore
        texto_sistema = ""
        if TextExportService:
            exporter = TextExportService()
            # construir conteúdo em memória
            parts: List[str] = []
            for n in nodes:
                if variante == 'baseline':
                    txt_val = n.get('baseline_text') or n.get('original_text', '')
                else:
                    txt_val = n.get('adapted_text') or n.get('baseline_text') or n.get('original_text', '')
                from ..core.placeholders import PlaceholderEncoder
                enc = PlaceholderEncoder()
                decoded = enc.decode_fragment(txt_val, n.get('placeholders', {}))
                from bs4 import BeautifulSoup as _BS
                soup = _BS(decoded, 'html.parser')
                plain = soup.get_text(separator=' ', strip=True)
                if plain:
                    parts.append(plain)
            texto_sistema = "\n\n".join(parts)
        else:
            # Fallback simples: concatenar textos sem decodificação
            parts = []
            for n in nodes:
                if variante == 'baseline':
                    parts.append(n.get('baseline_text') or n.get('original_text', ''))
                else:
                    parts.append(n.get('adapted_text') or n.get('baseline_text') or n.get('original_text', ''))
            texto_sistema = "\n\n".join([re.sub(r"\s+", " ", p).strip() for p in parts if p])

        # Texto humano: extrair do HTML
        from bs4 import BeautifulSoup
        soup_h = BeautifulSoup(human_html, 'html.parser')
        texto_humano = re.sub(r"\s+", " ", soup_h.get_text(' ', strip=True))

        refs = [texto_humano]
        hyps = [texto_sistema]

        # spaCy opcional
        nlp = None
        sintaxe_habilitada = False
        try:
            import spacy
            model_name = 'en_core_web_sm' if target_lang == 'en' else f'{target_lang}_core_news_sm'
            nlp = spacy.load(model_name)
            sintaxe_habilitada = True
        except Exception:
            nlp = None
            sintaxe_habilitada = False

        bleu = chrf = ter = None
        try:
            from sacrebleu import corpus_bleu, corpus_chrf, corpus_ter
            bleu = float(corpus_bleu(hyps, [refs]).score)
            chrf = float(corpus_chrf(hyps, [refs]).score)
            ter = float(corpus_ter(hyps, [refs]).score)
        except Exception:
            pass
        jaccard_medio = self.jaccard(hyps[0], refs[0]) if hyps[0] and refs[0] else None

        pos_media = None
        if nlp and hyps[0] and refs[0]:
            pos_media = self.pos_match_ratio(hyps[0], refs[0], nlp)

        # Resultado minimal para modo doc
        @dataclass
        class DocResult:
            documento: str
            idioma: str
            variante: str
            bleu: float | None
            chrf: float | None
            ter: float | None
            jaccard_medio: float | None
            pos_accuracy_media: float | None
            sintaxe_habilitada: bool
            texto_humano: str
            texto_sistema: str

        return DocResult(
            documento=documento,
            idioma=target_lang,
            variante=variante,
            bleu=bleu,
            chrf=chrf,
            ter=ter,
            jaccard_medio=jaccard_medio,
            pos_accuracy_media=pos_media,
            sintaxe_habilitada=sintaxe_habilitada,
            texto_humano=texto_humano,
            texto_sistema=texto_sistema,
        )
