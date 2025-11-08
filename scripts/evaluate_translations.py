"""Evaluation helpers for translation experiments."""
import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import sacrebleu
from sacrebleu.metrics import TER

WORKSPACE = Path(__file__).resolve().parents[1]
RESULTS_DIR = WORKSPACE / "results"
REFERENCES_DIR = WORKSPACE / "data" / "references"
GLOSSARY_DIR = WORKSPACE / "glossario"


def load_segments(path: Path) -> List[str]:
    content = path.read_text(encoding="utf-8")
    segments = [segment.strip() for segment in content.split("\n\n") if segment.strip()]
    return segments


def load_glossary(lang: str) -> Dict[str, str]:
    path = GLOSSARY_DIR / f"glossario_pt_{lang}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handler:
        data = json.load(handler)
    return {key.lower(): value for key, value in data.items()}


def compute_metrics(hypotheses: List[str], references: List[str], glossary: Dict[str, str]) -> Tuple[float, float, float]:
    bleu = sacrebleu.corpus_bleu(hypotheses, [references]).score
    ter_metric = TER().corpus_score(hypotheses, [references]).score
    term_acc = term_accuracy(hypotheses, references, glossary)
    return bleu, ter_metric, term_acc


def term_accuracy(hypotheses: List[str], references: List[str], glossary: Dict[str, str]) -> float:
    if not glossary:
        return 0.0
    total = 0
    hits = 0
    for hyp, ref in zip(hypotheses, references):
        for target in glossary.values():
            if target.lower() in ref.lower():
                total += 1
                if target.lower() in hyp.lower():
                    hits += 1
    return (hits / total) * 100 if total else 0.0


def evaluate_document(doc: str, lang: str) -> None:
    base = f"{doc}_{lang}"
    reference_path = REFERENCES_DIR / f"{base}_ref.txt"
    baseline_path = RESULTS_DIR / f"{doc}_baseline_{lang}.txt"
    adapted_path = RESULTS_DIR / f"{doc}_adapted_{lang}.txt"
    if not reference_path.exists():
        raise FileNotFoundError(f"Referencia ausente: {reference_path}")
    references = load_segments(reference_path)
    baseline = load_segments(baseline_path)
    adapted = load_segments(adapted_path)
    glossary = load_glossary(lang)
    print(f"Avaliando {doc} -> {lang}")
    baseline_bleu, baseline_ter, baseline_term = compute_metrics(baseline, references, glossary)
    adapted_bleu, adapted_ter, adapted_term = compute_metrics(adapted, references, glossary)
    print("Baseline:")
    print(f"  BLEU: {baseline_bleu:.2f}")
    print(f"  TER: {baseline_ter:.2f}")
    print(f"  Term Accuracy: {baseline_term:.2f}%")
    print("Adaptado:")
    print(f"  BLEU: {adapted_bleu:.2f}")
    print(f"  TER: {adapted_ter:.2f}")
    print(f"  Term Accuracy: {adapted_term:.2f}%")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compara traducoes baseline e adaptadas utilizando metricas padrao.")
    parser.add_argument("documento", help="Nome base do arquivo HTML sem extensao.")
    parser.add_argument("idioma", help="Idioma de avaliacao, ex: en ou es.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluate_document(args.documento, args.idioma)


if __name__ == "__main__":
    main()
