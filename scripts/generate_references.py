"""Generate draft reference translations from extracted text.

Segments each paragraph individually and produces automatic drafts that still
require human revision. Supports multiple target languages and any extracted
document present in data/extracted.
"""
import argparse
from pathlib import Path
import sys
from typing import List

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

WORKSPACE = Path(__file__).resolve().parents[1]
EXTRACTED_DIR = WORKSPACE / "data" / "extracted"
REF_DIR = WORKSPACE / "data" / "references"
REF_DIR.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera rascunhos de referencias automaticamente.")
    parser.add_argument(
        "document",
        nargs="?",
        default="InteriorTeor0",
        help="Nome base do arquivo em data/extracted (sem extensao). Ex.: InteriorTeor30",
    )
    parser.add_argument(
        "--languages",
        default="en,es",
        help="Idiomas destino separados por virgula (padrao: en,es).",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        help="Limite de tokens gerados por paragrafo.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Forca execucao em cpu/cuda ou usa auto (cuda se disponivel).",
    )
    return parser.parse_args()


def select_device(preference: str) -> torch.device:
    if preference == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA solicitado mas nao disponivel.")
        return torch.device("cuda")
    if preference == "cpu":
        return torch.device("cpu")
    # auto: cuda se tiver
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def translate_paragraphs(
    paragraphs: List[str],
    tokenizer: M2M100Tokenizer,
    model: M2M100ForConditionalGeneration,
    device: torch.device,
    src_lang: str,
    tgt_lang: str,
    max_new_tokens: int,
) -> List[str]:
    outputs: List[str] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        try:
            tokenizer.src_lang = src_lang
            encoded = tokenizer(
                paragraph,
                return_tensors="pt",
                truncation=True,
                max_length=1024,
            )
            encoded = {name: tensor.to(device) for name, tensor in encoded.items()}
            generation_kwargs = {"max_new_tokens": max_new_tokens}
            try:
                generation_kwargs["forced_bos_token_id"] = tokenizer.get_lang_id(tgt_lang)
            except Exception:
                pass
            with torch.no_grad():
                generated = model.generate(**encoded, **generation_kwargs)
            decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        except Exception as exc:
            decoded = f"[[ERROR TRANSLATING paragraph {index}: {exc}]]"
        outputs.append(decoded)
        print(f"Paragrafo {index}/{len(paragraphs)} traduzido -> {tgt_lang}", flush=True)
    return outputs


def main() -> None:
    args = parse_args()
    document = args.document
    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    if not languages:
        print("Nenhum idioma fornecido.")
        sys.exit(1)

    input_path = EXTRACTED_DIR / f"{document}.txt"
    if not input_path.exists():
        print(f"Arquivo de entrada nao encontrado: {input_path}")
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    paragraphs = [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]
    if not paragraphs:
        print("Nenhum paragrafo encontrado no texto extraido.")
        sys.exit(1)

    print(f"Documento {document} possui {len(paragraphs)} paragrafos.")
    device = select_device(args.device)
    print(f"Carregando modelo para {device}...")
    repo = "facebook/m2m100_418M"
    tokenizer = M2M100Tokenizer.from_pretrained(repo)
    model = M2M100ForConditionalGeneration.from_pretrained(repo)
    model.eval()
    model.to(device)

    for lang in languages:
        print(f"Traduzindo para {lang}...", flush=True)
        translated = translate_paragraphs(
            paragraphs=paragraphs,
            tokenizer=tokenizer,
            model=model,
            device=device,
            src_lang="pt",
            tgt_lang=lang,
            max_new_tokens=args.max_new_tokens,
        )
        output_path = REF_DIR / f"{document}_{lang}_ref.txt"
        output_path.write_text("\n\n".join(translated), encoding="utf-8")
        print(f"Arquivo salvo: {output_path}")


if __name__ == "__main__":
    main()
