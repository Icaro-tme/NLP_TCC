"""Wrapper around Hugging Face translation models used in the MVP."""

from __future__ import annotations

from dataclasses import dataclass
import os

os.environ["TRANSFORMERS_NO_TORCHVISION"] = "1"

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from .segmentation import get_sentence_segments

from .core.config import TranslationConfig


@dataclass
class TranslationGateway:
    """Handles model loading and inference for translation tasks."""

    config: TranslationConfig
    model: AutoModelForSeq2SeqLM | None = None
    tokenizer: AutoTokenizer | None = None
    device: torch.device | None = None

    def load(self) -> None:
        if self.model and self.tokenizer:
            return
        device = self._resolve_device()
        load_kwargs = {
            "low_cpu_mem_usage": True,
        }
        dtype: torch.dtype | None = None
        if self.config.fp16 and device.type == "cuda":
            dtype = torch.float16
        if dtype is not None:
            load_kwargs["torch_dtype"] = dtype
        if self.config.use_device_map and device.type == "cuda":
            load_kwargs["device_map"] = "auto"

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_name, use_fast=True
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.config.model_name,
            **load_kwargs,
        )
        if load_kwargs.get("device_map") is None:
            self.model.to(device)
        self.device = device

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        forced_terms: list[str] | None = None,
        num_beams: int | None = None,
    ) -> str:
        """Traduz um texto possivelmente longo.

        Se o número de tokens exceder a capacidade máxima do modelo (ex.: 1024 para m2m100),
        o texto é dividido em chunks menores baseados em sentenças para evitar warnings ou
        falhas de indexação. Mantém fluxo simples sem reordenação.
        """
        self.load()
        assert self.model is not None and self.tokenizer is not None
        tokenizer = self.tokenizer
        tokenizer.src_lang = source_lang
        # Logger leve para auditoria quando chunking for acionado.
        import logging
        logger = logging.getLogger("translate")
        if not logger.handlers:
            logging.basicConfig(level=logging.INFO)

        # Tokeniza inicialmente para medir tamanho. Sem padding/truncation para detectar overflow.
        probe = tokenizer(text, return_tensors="pt", padding=False, add_special_tokens=True)
        seq_len = int(probe["input_ids"].shape[1])
        max_pos = getattr(self.model.config, "max_position_embeddings", None) or getattr(
            self.model.config, "max_length", 1024
        )

        # Se o texto excede o limite, realizar chunking por sentenças acumulando até limite aproximado.
        if seq_len > max_pos:
            # Segmentação de sentenças; pode exigir spaCy conforme configuração.
            require_spacy = bool(getattr(self.config, "require_spacy_for_chunking", True))
            sentences, method = get_sentence_segments(text, lang=source_lang, require_spacy=require_spacy)
            logger.info(
                "[CHUNK] seq_len=%d > max_pos=%d | method=%s | src_lang=%s",
                seq_len,
                max_pos,
                method,
                source_lang,
            )
            chunks: list[str] = []
            current: list[str] = []
            current_tokens = 0
            for sent in sentences:
                sent_probe = tokenizer(sent, return_tensors="pt", padding=False, add_special_tokens=True)
                sent_len = int(sent_probe["input_ids"].shape[1])
                # Se a sentença isolada já estoura, forçar truncação direta.
                if sent_len > max_pos:
                    truncated_ids = sent_probe["input_ids"][0][: max_pos]
                    sent = tokenizer.decode(truncated_ids, skip_special_tokens=True)
                    sent_len = max_pos
                if current_tokens + sent_len > max_pos and current:
                    chunks.append(" ".join(current).strip())
                    current = [sent]
                    current_tokens = sent_len
                else:
                    current.append(sent)
                    current_tokens += sent_len
            if current:
                chunks.append(" ".join(current).strip())
            logger.info("[CHUNK] built %d chunks (approx token-bounded)", len(chunks))
            # Traduz cada chunk separadamente e concatena com espaço duplo para preservar respiros.
            translated_chunks: list[str] = []
            for i, chunk in enumerate(chunks):
                # Forced terms somente no primeiro chunk para reduzir risco de excesso de constraints.
                t = self._translate_chunk(
                    tokenizer,
                    chunk,
                    source_lang,
                    target_lang,
                    max_length,
                    forced_terms if i == 0 else None,
                    num_beams,
                )
                translated_chunks.append(t.strip())
            return "  ".join(translated_chunks).strip()

        # Caso normal (dentro do limite de posição)
        return self._translate_chunk(
            tokenizer,
            text,
            source_lang,
            target_lang,
            max_length,
            forced_terms,
            num_beams,
        )

    def _translate_chunk(
        self,
        tokenizer: AutoTokenizer,
        text: str,
        source_lang: str,
        target_lang: str,
        max_length: int | None,
        forced_terms: list[str] | None,
        num_beams: int | None,
    ) -> str:
        tokens = tokenizer(
            text,
            return_tensors="pt",
            padding=False,
        )
        if self.device:
            tokens = {k: v.to(self.device) for k, v in tokens.items()}
        if hasattr(tokenizer, "get_lang_id"):
            forced_bos_token_id = tokenizer.get_lang_id(target_lang)
        else:
            forced_bos_token_id = tokenizer.lang_code_to_id[target_lang]
        generate_kwargs = {
            "forced_bos_token_id": forced_bos_token_id,
            "max_length": max_length or self.config.max_length,
        }
        force_words_ids = []
        if forced_terms:
            for term in forced_terms:
                term = term.strip()
                if not term:
                    continue
                ids = tokenizer(term, add_special_tokens=False).input_ids
                if ids:
                    force_words_ids.append(ids)
            if force_words_ids:
                generate_kwargs["num_beams"] = max(num_beams or 4, len(force_words_ids) + 1)
                generate_kwargs["force_words_ids"] = force_words_ids
        generated_tokens = self.model.generate(
            **tokens,
            **generate_kwargs,
        )
        decoded = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
        return decoded[0]

    def _resolve_device(self) -> torch.device:
        if self.config.device == "cuda" and torch.cuda.is_available():
            return torch.device("cuda")
        if self.config.device == "cpu":
            return torch.device("cpu")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
