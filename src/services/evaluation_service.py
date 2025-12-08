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
import hashlib
import json
from pathlib import Path

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
        self.cache_dir = paths.data_dir / "evaluation_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- Sistema de Cache com Invalidação Automática -----------------
    @staticmethod
    def _compute_hash(content: str) -> str:
        """Calcula MD5 hash do conteúdo para detecção de mudanças."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_cache_path(self, documento: str, variante: str, target_lang: str, human_hash: str) -> Path:
        """Retorna path do cache incluindo hash do conteúdo humano."""
        return self.cache_dir / f"{documento}_{variante}_{target_lang}_{human_hash}.json"

    def _get_system_file_mtime(self, documento: str, variante: str, target_lang: str) -> float:
        """Retorna timestamp de modificação do arquivo da variante exportada."""
        if variante == 'crude':
            # Crude usa original PT indexado + LibreTranslate on-demand
            system_file = self.paths.data_dir / "extracted" / f"{documento}_indexed.html"
        else:
            # Baseline/Adapted usam arquivos exportados em results/html/
            system_file = self.paths.results_dir / "html" / f"{documento}_{variante}_{target_lang}.html"
        
        if not system_file.exists():
            return 0.0
        return system_file.stat().st_mtime

    def _load_from_cache(self, cache_path: Path, expected_mtime: float) -> Optional[Dict]:
        """Carrega resultado do cache se existir, for válido e não estiver desatualizado.
        
        Args:
            cache_path: Path do arquivo de cache
            expected_mtime: Timestamp esperado do arquivo da variante (para invalidação)
        """
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            
            # Valida se o cache não está desatualizado (arquivo da variante foi re-exportado)
            cached_mtime = cached.get('_system_file_mtime', 0.0)
            if cached_mtime < expected_mtime:
                # Cache desatualizado: arquivo da variante foi modificado após criação do cache
                return None
            
            return cached
        except Exception:
            return None

    def _save_to_cache(self, cache_path: Path, data: Dict, system_file_mtime: float) -> None:
        """Salva resultado no cache com timestamp do arquivo da variante.
        
        Args:
            cache_path: Path do arquivo de cache
            data: Dados da avaliação a cachear
            system_file_mtime: Timestamp do arquivo da variante (para validação futura)
        """
        try:
            # Adiciona metadata de invalidação
            data['_system_file_mtime'] = system_file_mtime
            data['_cached_at'] = Path(cache_path).stat().st_mtime if cache_path.exists() else 0.0
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Cache é opcional, não falhar se não conseguir salvar

    def _invalidate_old_caches(self, documento: str, variante: str, target_lang: str, current_hash: str) -> None:
        """Remove caches antigos com hashes diferentes (conteúdo humano mudou)."""
        pattern = f"{documento}_{variante}_{target_lang}_*.json"
        for old_cache in self.cache_dir.glob(pattern):
            if current_hash not in old_cache.name:
                try:
                    old_cache.unlink()
                except Exception:
                    pass

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

        Sistema de cache inteligente:
        - Hash MD5 do human_html detecta se conteúdo mudou
        - Cache invalidado automaticamente quando human_html é diferente
        - Suporta variantes: baseline, adapted, crude (LibreTranslate on-demand)
        """
        # 1. Calcula hash do conteúdo humano + timestamp do arquivo da variante
        human_hash = self._compute_hash(human_html)
        system_mtime = self._get_system_file_mtime(documento, variante, target_lang)
        cache_path = self._get_cache_path(documento, variante, target_lang, human_hash)
        
        # 2. Tenta carregar do cache (valida se arquivo da variante não foi re-exportado)
        cached = self._load_from_cache(cache_path, system_mtime)
        if cached:
            # Cache hit: retorna resultado anterior
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
                cached: bool = True
            
            return DocResult(
                documento=cached['documento'],
                idioma=cached['idioma'],
                variante=cached['variante'],
                bleu=cached.get('bleu'),
                wer=cached.get('wer'),
                per=cached.get('per'),
                ter=cached.get('ter'),
                texto_humano=cached.get('texto_humano', ''),
                texto_sistema=cached.get('texto_sistema', ''),
                cached=True
            )
        
        # 3. Cache miss: processa avaliação completa
        document_id = self.doc_repo.find_document_id(documento, source_lang, target_lang)
        if document_id is None:
            raise ValueError(f"Documento não encontrado para {documento} {source_lang}->{target_lang}")
        
        from ..html_io import read_html
        
        def _plain_from_html(html_str: str) -> str:
            soup = BeautifulSoup(html_str, 'html.parser')
            text = soup.get_text(' ', strip=True)
            text = html_module.unescape(text)
            text = text.replace('\xa0', ' ')
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r"\s+", " ", text).strip()
            return text

        # Se variante é 'crude', traduz o texto ORIGINAL (PT) via LibreTranslate
        if variante == 'crude':
            from ..backends.libretranslate_backend import LibreTranslateClient
            
            # Extrai texto original PT do HTML indexado (fonte canônica)
            resultados_original = self.paths.data_dir / "extracted" / f"{documento}_indexed.html"
            if not resultados_original.exists():
                raise FileNotFoundError(
                    f"HTML original indexado não encontrado: {resultados_original}. "
                    f"Execute o processamento do documento primeiro."
                )
            
            html_original = read_html(resultados_original)
            texto_original_pt = _plain_from_html(html_original)
            
            # Traduz via LibreTranslate (determinístico)
            client = LibreTranslateClient()
            try:
                texto_sistema = client.translate(texto_original_pt, source_lang=source_lang, target_lang=target_lang)
            except Exception as e:
                raise RuntimeError(f"Erro ao traduzir via LibreTranslate: {e}")
        
        else:
            # Para baseline/adapted: lê HTML exportado (fonte canônica)
            resultados_html = self.paths.results_dir / "html" / f"{documento}_{variante}_{target_lang}.html"
            if not resultados_html.exists():
                raise FileNotFoundError(
                    f"HTML da variante '{variante}' não encontrado: {resultados_html}. "
                    f"Exporte a variante primeiro usando o endpoint /exportar/html antes de avaliar."
                )
            
            html_sistema = read_html(resultados_html)
            texto_sistema = _plain_from_html(html_sistema)

        # Texto humano bruto (referência para comparação)
        texto_humano = _plain_from_html(human_html)

        # WER e PER usando biblioteca jiwer (padrão da indústria)
        wer = per = None
        try:
            from jiwer import wer as compute_wer, compute_measures
            # WER: Word Error Rate (Levenshtein distance normalizado)
            wer = float(compute_wer(texto_humano, texto_sistema))
            
            # PER: Position-Independent Error Rate
            # jiwer não tem PER nativo, mas podemos calcular via medidas intermediárias
            measures = compute_measures(texto_humano, texto_sistema)
            # PER = (S + D + I - M) / N, onde M = matches após ordenação bag-of-words
            # Aproximação: usar WIL (Word Information Lost) ou implementação manual validada
            from collections import Counter
            ref_words = texto_humano.lower().split()
            hyp_words = texto_sistema.lower().split()
            if ref_words:
                cref = Counter(ref_words)
                chyp = Counter(hyp_words)
                correct = sum(min(cref[w], chyp[w]) for w in cref)
                per = float((len(ref_words) - correct) / len(ref_words))
        except Exception as e:
            # Fallback para None se jiwer não estiver instalado
            pass

        # BLEU e TER usando SacreBLEU (padrão de referência)
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
            cached: bool = False

        result = DocResult(
            documento=documento,
            idioma=target_lang,
            variante=variante,
            bleu=bleu,
            wer=wer,
            per=per,
            ter=ter,
            texto_humano=texto_humano,
            texto_sistema=texto_sistema,
            cached=False
        )
        
        # 4. Salva no cache com timestamp do arquivo da variante e remove caches antigos
        cache_data = {
            'documento': documento,
            'idioma': target_lang,
            'variante': variante,
            'bleu': bleu,
            'wer': wer,
            'per': per,
            'ter': ter,
            'texto_humano': texto_humano,
            'texto_sistema': texto_sistema,
        }
        self._save_to_cache(cache_path, cache_data, system_mtime)
        self._invalidate_old_caches(documento, variante, target_lang, human_hash)
        
        return result
