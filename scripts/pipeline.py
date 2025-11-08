"""Pipeline to extract, translate, and adapt legal HTML documents."""
import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import time

from bs4 import BeautifulSoup
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

WORKSPACE = Path(__file__).resolve().parents[1]
SOURCE_HTML_DIR = WORKSPACE / "arquivos_juridicos"
EXTRACTED_DIR = WORKSPACE / "data" / "extracted"
GLOSSARY_DIR = WORKSPACE / "glossario"
DEFINITIONS_DIR = WORKSPACE / "corpus" / "definicoes"
RESULTS_DIR = WORKSPACE / "results"

MT_MODELS = {
    "en": {"repo": "facebook/m2m100_418M", "src_lang": "pt", "tgt_lang": "en"},
    "es": {"repo": "facebook/m2m100_418M", "src_lang": "pt", "tgt_lang": "es"},
}
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def ensure_dirs() -> None:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_glossary(lang: str) -> Dict[str, str]:
    glossary_path = GLOSSARY_DIR / f"glossario_pt_{lang}.json"
    if not glossary_path.exists():
        return {}
    with glossary_path.open("r", encoding="utf-8") as handler:
        data = json.load(handler)
    normalized = {key.lower(): value for key, value in data.items()}
    return normalized


def load_definitions() -> List[str]:
    definitions: List[str] = []
    if not DEFINITIONS_DIR.exists():
        return definitions
    for file_path in sorted(DEFINITIONS_DIR.glob("*.txt")):
        with file_path.open("r", encoding="utf-8") as handler:
            content = handler.read().strip()
            if content:
                definitions.append(content)
    return definitions


def extract_text_from_html(html_path: Path) -> str:
    with html_path.open("r", encoding="utf-8") as handler:
        soup = BeautifulSoup(handler, "lxml")
    paragraphs = [node.get_text(" ", strip=True) for node in soup.find_all("p")]
    return "\n".join(paragraphs)


def save_extracted_text(base_name: str, content: str) -> None:
    target = EXTRACTED_DIR / f"{base_name}.txt"
    with target.open("w", encoding="utf-8") as handler:
        handler.write(content)


def chunk_text(content: str, max_chars: int) -> List[str]:
    paragraphs = [paragraph.strip() for paragraph in content.split("\n") if paragraph.strip()]
    blocks: List[str] = []
    current: List[str] = []
    size = 0
    for paragraph in paragraphs:
        length = len(paragraph)
        if size + length > max_chars and current:
            blocks.append(" ".join(current))
            current = [paragraph]
            size = length
        else:
            current.append(paragraph)
            size += length
    if current:
        blocks.append(" ".join(current))
    return blocks


def load_model(repo_id: str) -> Tuple[AutoTokenizer, AutoModelForSeq2SeqLM]:
    tokenizer = AutoTokenizer.from_pretrained(repo_id)
    model = AutoModelForSeq2SeqLM.from_pretrained(repo_id)
    return tokenizer, model


def translate(
    text: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForSeq2SeqLM,
    max_new_tokens: int,
    source_lang: str,
    target_lang: str,
) -> str:
    if hasattr(tokenizer, "src_lang"):
        tokenizer.src_lang = source_lang
    encoded = tokenizer(text, return_tensors="pt", truncation=True)
    generation_kwargs = {"max_new_tokens": max_new_tokens}
    if hasattr(tokenizer, "get_lang_id"):
        try:
            generation_kwargs["forced_bos_token_id"] = tokenizer.get_lang_id(target_lang)
        except KeyError:
            pass
    with torch.no_grad():
        output = model.generate(**encoded, **generation_kwargs)
    return tokenizer.decode(output[0], skip_special_tokens=True)


def annotate_with_glossary(text: str, glossary: Dict[str, str]) -> str:
    if not glossary:
        return text
    annotated = text
    for term, target in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(term)}\b", flags=re.IGNORECASE)

        def _inject(match: re.Match) -> str:
            original = match.group(0)
            normalized = original.lower()
            if normalized.endswith(f"({target.lower()})"):
                return original
            return f"{original} ({target})"

        annotated = pattern.sub(_inject, annotated)
    return annotated


def build_rag_context(encoder: SentenceTransformer, cache: Dict[str, torch.Tensor], definitions: List[str], text: str, top_k: int) -> str:
    if not definitions:
        return ""
    if "definitions" not in cache:
        cache["definitions"] = encoder.encode(definitions, convert_to_tensor=True, show_progress_bar=False)
    query_embedding = encoder.encode(text, convert_to_tensor=True, show_progress_bar=False)
    similarities = torch.matmul(cache["definitions"], query_embedding)
    top = torch.topk(similarities, k=min(top_k, len(definitions)))
    selected = [definitions[index] for index in top.indices]
    return "\n".join(selected)


def generate_outputs(
    blocks: Iterable[str],
    lang: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForSeq2SeqLM,
    glossary: Dict[str, str],
    encoder: Optional[SentenceTransformer],
    definitions: List[str],
    rag_cache: Dict[str, torch.Tensor],
    max_new_tokens: int,
    use_glossary: bool,
    use_rag: bool,
    source_lang: str,
    target_lang: str,
) -> Tuple[List[str], List[str]]:
    # This function remains for backwards compatibility but will process all
    # blocks in-memory. For incremental saving we call translate_block in the
    # pipeline loop below.
    baseline: List[str] = []
    adapted: List[str] = []
    for block in blocks:
        baseline_translation = translate(
            block,
            tokenizer,
            model,
            max_new_tokens,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        baseline.append(baseline_translation)
        enriched_block = block
        if use_glossary:
            enriched_block = annotate_with_glossary(enriched_block, glossary)
        if use_rag and encoder is not None:
            context = build_rag_context(encoder, rag_cache, definitions, block, top_k=3)
            if context:
                enriched_block = f"{enriched_block}\n\nContexto juridico:\n{context}"
        adapted_translation = translate(
            enriched_block,
            tokenizer,
            model,
            max_new_tokens,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        if use_glossary:
            adapted_translation = enforce_glossary(adapted_translation, glossary)
        adapted.append(adapted_translation)
    return baseline, adapted


def translate_block(
    block: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForSeq2SeqLM,
    glossary: Dict[str, str],
    encoder: Optional[SentenceTransformer],
    definitions: List[str],
    rag_cache: Dict[str, torch.Tensor],
    max_new_tokens: int,
    use_glossary: bool,
    use_rag: bool,
    source_lang: str,
    target_lang: str,
) -> Tuple[str, str]:
    """Translate a single block and return (baseline, adapted)."""
    baseline_translation = translate(
        block,
        tokenizer,
        model,
        max_new_tokens,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    enriched_block = block
    if use_glossary:
        enriched_block = annotate_with_glossary(enriched_block, glossary)
    if use_rag and encoder is not None:
        context = build_rag_context(encoder, rag_cache, definitions, block, top_k=3)
        if context:
            enriched_block = f"{enriched_block}\n\nContexto juridico:\n{context}"
    adapted_translation = translate(
        enriched_block,
        tokenizer,
        model,
        max_new_tokens,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    if use_glossary:
        adapted_translation = enforce_glossary(adapted_translation, glossary)
    return baseline_translation, adapted_translation


def append_result_block(base_name: str, lang: str, baseline_text: str, adapted_text: str) -> None:
    """Append a single translated block to the results files (incremental checkpoint)."""
    baseline_path = RESULTS_DIR / f"{base_name}_baseline_{lang}.txt"
    adapted_path = RESULTS_DIR / f"{base_name}_adapted_{lang}.txt"
    sep = "\n\n"
    # Append baseline
    with baseline_path.open("a", encoding="utf-8") as f:
        try:
            exists_and_nonempty = baseline_path.stat().st_size > 0
        except Exception:
            exists_and_nonempty = False
        if exists_and_nonempty:
            f.write(sep)
        f.write(baseline_text)
    # Append adapted
    with adapted_path.open("a", encoding="utf-8") as f:
        try:
            exists_and_nonempty = adapted_path.stat().st_size > 0
        except Exception:
            exists_and_nonempty = False
        if exists_and_nonempty:
            f.write(sep)
        f.write(adapted_text)


def enforce_glossary(text: str, glossary: Dict[str, str]) -> str:
    if not glossary:
        return text
    corrected = text
    for term, target in sorted(glossary.items(), key=lambda item: len(item[0]), reverse=True):
        source_pattern = re.compile(rf"\b{re.escape(term)}\b", flags=re.IGNORECASE)
        corrected = source_pattern.sub(target, corrected)
    return corrected


def write_results(base_name: str, lang: str, baseline: List[str], adapted: List[str]) -> None:
    baseline_path = RESULTS_DIR / f"{base_name}_baseline_{lang}.txt"
    adapted_path = RESULTS_DIR / f"{base_name}_adapted_{lang}.txt"
    baseline_path.write_text("\n\n".join(baseline), encoding="utf-8")
    adapted_path.write_text("\n\n".join(adapted), encoding="utf-8")


def run_pipeline(languages: List[str], max_chars: int, max_new_tokens: int, use_glossary: bool, use_rag: bool) -> None:
    ensure_dirs()
    html_files = sorted(SOURCE_HTML_DIR.glob("*.html"))
    if not html_files:
        print("Nenhum HTML encontrado em arquivos_juridicos")
        return
    definitions = load_definitions()
    encoder = SentenceTransformer(EMBEDDING_MODEL) if use_rag and definitions else None
    rag_cache: Dict[str, torch.Tensor] = {}
    model_cache: Dict[str, Tuple[AutoTokenizer, AutoModelForSeq2SeqLM]] = {}
    glossaries: Dict[str, Dict[str, str]] = {}
    for lang in languages:
        glossaries[lang] = load_glossary(lang)
    for html_path in html_files:
        base_name = html_path.stem
        print(f"Processando {html_path.name}")
        content = extract_text_from_html(html_path)
        save_extracted_text(base_name, content)
        blocks = chunk_text(content, max_chars=max_chars)
        for lang in languages:
            config = MT_MODELS.get(lang)
            if config is None:
                print(f"Idioma nao suportado: {lang}")
                continue
            repo_id = config["repo"]
            if repo_id not in model_cache:
                model_cache[repo_id] = load_model(repo_id)
            tokenizer, model = model_cache[repo_id]
            glossary = glossaries[lang]
            # Remove any pre-existing partial files for a clean run
            try:
                (RESULTS_DIR / f"{base_name}_baseline_{lang}.txt").unlink(missing_ok=True)
            except TypeError:
                # Python <3.8 fallback
                baseline_tmp = RESULTS_DIR / f"{base_name}_baseline_{lang}.txt"
                if baseline_tmp.exists():
                    baseline_tmp.unlink()
            try:
                (RESULTS_DIR / f"{base_name}_adapted_{lang}.txt").unlink(missing_ok=True)
            except TypeError:
                adapted_tmp = RESULTS_DIR / f"{base_name}_adapted_{lang}.txt"
                if adapted_tmp.exists():
                    adapted_tmp.unlink()

            total = len(blocks)
            start_time = time.perf_counter()
            for idx, block in enumerate(blocks, start=1):
                block_start = time.perf_counter()
                baseline_text, adapted_text = translate_block(
                    block=block,
                    tokenizer=tokenizer,
                    model=model,
                    glossary=glossary,
                    encoder=encoder,
                    definitions=definitions,
                    rag_cache=rag_cache,
                    max_new_tokens=max_new_tokens,
                    use_glossary=use_glossary,
                    use_rag=use_rag,
                    source_lang=config["src_lang"],
                    target_lang=config["tgt_lang"],
                )
                append_result_block(base_name, lang, baseline_text, adapted_text)
                block_elapsed = time.perf_counter() - block_start
                overall_elapsed = time.perf_counter() - start_time
                print(f"[{base_name}][{lang}] Block {idx}/{total} done (block {block_elapsed:.1f}s, total {overall_elapsed:.1f}s)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Processa documentos juridicos em HTML e gera traducoes.")
    parser.add_argument("--languages", default="en,es", help="Idiomas destino separados por virgula.")
    parser.add_argument("--max-chars", type=int, default=800, help="Numero maximo de caracteres por bloco.")
    parser.add_argument("--max-new-tokens", type=int, default=256, help="Limite de tokens gerados por traducao.")
    parser.add_argument("--no-glossary", action="store_true", help="Desativa a anotacao de glossario.")
    parser.add_argument("--rag", action="store_true", help="Ativa busca de contexto via RAG.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    run_pipeline(
        languages=languages,
        max_chars=getattr(args, "max_chars"),
        max_new_tokens=getattr(args, "max_new_tokens"),
        use_glossary=not args.no_glossary,
        use_rag=args.rag,
    )


if __name__ == "__main__":
    main()
