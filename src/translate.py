"""Wrapper around Hugging Face translation models used in the MVP."""

from __future__ import annotations

from dataclasses import dataclass
import os

os.environ["TRANSFORMERS_NO_TORCHVISION"] = "1"

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

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
    ) -> str:
        self.load()
        assert self.model is not None and self.tokenizer is not None
        tokenizer = self.tokenizer
        tokenizer.src_lang = source_lang
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
        generated_tokens = self.model.generate(
            **tokens,
            forced_bos_token_id=forced_bos_token_id,
            max_length=max_length or self.config.max_length,
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
