"""Serviço de avaliação da tradução comparando variante do sistema com tradução humana.

Métricas relevantes (prioridade do TCC):
- BLEU: similaridade n-gram com penalidade de brevidade.
- WER: taxa de erros palavra a palavra via distância de Levenshtein.
- PER: taxa de erros independente de posição (bag-of-words).
- TER: taxa de edição mínima (sacrebleu: corpus_ter).

Notas de implementação:
- chrF, Jaccard e POS foram mantidas apenas no método antigo `compute` (por nó), mas
    para avaliação de documento completo (`compute_doc`) retornamos somente BLEU, WER, PER, TER.
- Decodificamos placeholders para gerar texto bruto contínuo preservando conteúdo inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from bs4 import BeautifulSoup
import unicodedata
import html as html_module

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
        """Avalia métricas globais (BLEU, WER, PER, TER) comparando texto humano vs texto da variante.

        Passos:
        1. Concatena textos dos nós (baseline/adapted + fallback original) decodificando placeholders.
        2. Extrai texto humano bruto do HTML enviado.
        3. Calcula BLEU e TER via sacrebleu; WER e PER via implementações internas.
        """
        document_id = self.doc_repo.find_document_id(documento, source_lang, target_lang)
        if document_id is None:
            raise ValueError(f"Documento não encontrado para {documento} {source_lang}->{target_lang}")
        # Em vez de reconstruir via nós, lê diretamente o HTML exportado da variante
        from ..html_io import read_html
        resultados_html = self.paths.results_dir / "html" / f"{documento}_{variante}_{target_lang}.html"
        if not resultados_html.exists():
            # Se não existir, tenta versão gerada por CLI com sufixo diferente (fallback)
            alt = self.paths.results_dir / "html" / f"{documento}_adapted_{target_lang}.html" if variante == 'adapted' else self.paths.results_dir / "html" / f"{documento}_baseline_{target_lang}.html"
            resultados_html = alt if alt.exists() else resultados_html
        def _plain_from_html(html_str: str) -> str:
            soup = BeautifulSoup(html_str, 'html.parser')
            text = soup.get_text(' ', strip=True)
            text = html_module.unescape(text)
            text = text.replace('\xa0', ' ')
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r"\s+", " ", text).strip()
            return text

        if resultados_html.exists():
            html_sistema = read_html(resultados_html)
            texto_sistema = _plain_from_html(html_sistema)
        else:
            # Fallback final: concatenação via banco de dados (como antes)
            nodes = self.node_repo.list_nodes(document_id)
            partes_sistema: List[str] = []
            for n in nodes:
                if variante == 'baseline':
                    txt_val = n.get('baseline_text') or n.get('original_text', '')
                else:
                    txt_val = n.get('adapted_text') or n.get('human_text') or n.get('baseline_text') or n.get('original_text', '')
                plain = _plain_from_html(txt_val)
                if plain:
                    partes_sistema.append(plain)
            texto_sistema = "\n\n".join(partes_sistema)

        # Texto humano bruto
        texto_humano = _plain_from_html(human_html)

        # Tokenização simples por espaços
        def _tokens(t: str) -> List[str]:
            return [x for x in re.split(r"\s+", t.strip()) if x]

        ref_tokens = _tokens(texto_humano)
        hyp_tokens = _tokens(texto_sistema)

        # WER (Levenshtein)
        def _wer(ref: List[str], hyp: List[str]) -> Optional[float]:
            if not ref:
                return None
            # matriz (len_ref+1 x len_hyp+1)
            m, n = len(ref), len(hyp)
            dp = [[0]*(n+1) for _ in range(m+1)]
            for i in range(m+1): dp[i][0] = i
            for j in range(n+1): dp[0][j] = j
            for i in range(1, m+1):
                for j in range(1, n+1):
                    cost = 0 if ref[i-1] == hyp[j-1] else 1
                    dp[i][j] = min(
                        dp[i-1][j] + 1,      # deleção
                        dp[i][j-1] + 1,      # inserção
                        dp[i-1][j-1] + cost  # substituição
                    )
            return dp[m][n] / m if m > 0 else None

        # PER (position-independent error rate)
        def _per(ref: List[str], hyp: List[str]) -> Optional[float]:
            if not ref:
                return None
            from collections import Counter
            cref = Counter(ref)
            chyp = Counter(hyp)
            correct = sum(min(cref[w], chyp[w]) for w in cref)
            return (len(ref) - correct) / len(ref)

        wer = _wer(ref_tokens, hyp_tokens)
        per = _per(ref_tokens, hyp_tokens)

        bleu = ter = None
        try:
            from sacrebleu import corpus_bleu, corpus_ter
            bleu = float(corpus_bleu([texto_sistema], [[texto_humano]]).score)
            ter = float(corpus_ter([texto_sistema], [[texto_humano]]).score)
        except Exception:
            pass

        @dataclass
        class DocResult:
            documento: str
            idioma: str
            variante: str
            bleu: float | None
            wer: float | None
            per: float | None
            ter: float | None
            texto_humano: str
            texto_sistema: str

        return DocResult(
            documento=documento,
            idioma=target_lang,
            variante=variante,
            bleu=bleu,
            wer=wer,
            per=per,
            ter=ter,
            texto_humano=texto_humano,
            texto_sistema=texto_sistema,
        )
