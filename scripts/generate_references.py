"""Generate draft reference translations (EN and ES) from extracted text.
This script is conservative: it segments by paragraphs and translates each paragraph individually.
Run while the main pipeline may be idle; it will print progress.
"""
from pathlib import Path
import sys
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
import torch

WORKSPACE = Path(__file__).resolve().parents[1]
EXTRACTED_DIR = WORKSPACE / "data" / "extracted"
REF_DIR = WORKSPACE / "data" / "references"
REF_DIR.mkdir(parents=True, exist_ok=True)

INPUT = EXTRACTED_DIR / "InteriorTeor0.txt"
OUT_EN = REF_DIR / "InteriorTeor0_en_ref.txt"
OUT_ES = REF_DIR / "InteriorTeor0_es_ref.txt"

if not INPUT.exists():
    print(f"Input not found: {INPUT}")
    sys.exit(1)

text = INPUT.read_text(encoding="utf-8")
# segment by paragraphs
paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
if not paragraphs:
    print("No paragraphs found in input.")
    sys.exit(1)

print(f"Found {len(paragraphs)} paragraphs; loading model...", flush=True)
repo = "facebook/m2m100_418M"
# load tokenizer & model
tokenizer = M2M100Tokenizer.from_pretrained(repo)
model = M2M100ForConditionalGeneration.from_pretrained(repo)
model.eval()
if torch.cuda.is_available():
    model.to("cuda")

max_new_tokens = 256

def translate_paragraphs(paragraphs, src_lang, tgt_lang):
    out_lines = []
    for i, p in enumerate(paragraphs, start=1):
        try:
            tokenizer.src_lang = src_lang
            encoded = tokenizer(p, return_tensors="pt", truncation=True, max_length=1024)
            if torch.cuda.is_available():
                for k,v in encoded.items():
                    encoded[k] = v.to("cuda")
            gen_kwargs = {"max_new_tokens": max_new_tokens}
            # try to set forced_bos if available
            try:
                gen_kwargs["forced_bos_token_id"] = tokenizer.get_lang_id(tgt_lang)
            except Exception:
                pass
            with torch.no_grad():
                out = model.generate(**encoded, **gen_kwargs)
            decoded = tokenizer.batch_decode(out, skip_special_tokens=True)[0]
        except Exception as e:
            decoded = f"[[ERROR TRANSLATING paragraph {i}: {e}]]"
        out_lines.append(decoded)
        print(f"Translated paragraph {i}/{len(paragraphs)} -> {tgt_lang}", flush=True)
    return out_lines

print("Translating to English...", flush=True)
refs_en = translate_paragraphs(paragraphs, src_lang="pt", tgt_lang="en")
print("Translating to Spanish...", flush=True)
refs_es = translate_paragraphs(paragraphs, src_lang="pt", tgt_lang="es")

# write outputs separated by blank lines
OUT_EN.write_text("\n\n".join(refs_en), encoding="utf-8")
OUT_ES.write_text("\n\n".join(refs_es), encoding="utf-8")

print(f"Wrote {OUT_EN} and {OUT_ES}")
