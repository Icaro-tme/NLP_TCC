"""CLI do MVP do projeto (entrada principal de linha de comando).

Legenda / Glossário de termos usados neste script:
- Nó (node): um trecho textual extraído do DOM do HTML (ex.: texto de um parágrafo ou elemento).
- Placeholder <ph>: marcador inline que preserva conteúdo especial/variáveis durante a tradução.
- Estratégias de tradução (mode):
    - node: traduz cada nó isoladamente (rápido, porém menos contexto, qualidade inferior em geral).
    - window: agrupa nós vizinhos em janelas para dar contexto local e depois reparte a tradução pelos nós originais.
    - doc: lineariza o documento inteiro com marcadores <N#> para traduzir de uma vez, mapeando de volta por marcador.
    - doc-sintatico: variação do doc com heurísticas sintáticas para repartir nós curtos sem perder fluidez.
- Backends de tradução (backend):
    - hf: modelo seq2seq via Hugging Face (ex.: m2m100).
    - google: LLM (Gemini) com prompt para preservar estrutura e placeholders.
- RAG (Retrieval-Augmented Generation): recuperação de trechos relevantes (glossário/corpus) para compor um contexto que orienta a tradução (doc-level).

Este script expõe subcomandos:
- ingest: lê um HTML, indexa nós (com placeholders) e persiste no banco.
- process: traduz o documento com a estratégia e backend selecionados.
- export: reconstrói HTML com a variante desejada (baseline/adapted/human).
- export-text: extrai o texto traduzido em .txt (para avaliação/comparação).
 
 Notas importantes:
 - Logger: usamos `get_logger()` (src/core/logging_utils.py) para registrar eventos na execução. É um logger configurado para console; mensagens estão em Português para facilitar auditoria humana.
 - SQLite: persistimos um índice de documentos e nós (trechos do DOM) para viabilizar (1) reprocessar/exportar sem reindexar HTML, (2) armazenar traduções por nó e idioma, (3) comparar variantes (baseline/adapted/human) no mesmo documento. O banco fica em data/db/nlp_tcc.sqlite.
 - Convenção de nomes com sublinhado: funções iniciadas com `_` (ex.: `_ingest_internal`) são consideradas utilitários internos do módulo (convenção Python), não parte da interface pública da CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List


# Ensure project root (parent of scripts/) is on the import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Lightweight .env loader (avoids external dependency). We only set variables not already set.
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        val = raw_val.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = val


from src.core.config import PathsConfig, PipelineConfig, TranslationConfig, RagConfig
from src.core.logging_utils import get_logger, log_time
from src.dom_indexer import index_html
from src.html_io import read_html, write_html
from src.persistence.db import Database
from src.persistence.repos import DocumentRepository, NodeRepository
from src.services.export_service import ExportService
from src.services.translation_service import TranslationService
from src.services.doc_level_service import DocLevelTranslationService
from src.services.doc_syntactic_service import DocSyntacticTranslationService
from src.telemetry.context import (
    emit_language_finish,
    emit_language_start,
    translation_observer,
)
from src.translate import TranslationGateway


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NLP TCC MVP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingerir HTML e indexar nós")
    ingest_parser.add_argument("--input", required=True, help="Caminho para o arquivo HTML")
    ingest_parser.add_argument(
        "--languages",
        default="en",
        help="Lista de idiomas alvo separada por vírgula (padrão: en)",
    )
    ingest_parser.add_argument("--source-lang", default="pt", help="Código do idioma de origem")
    ingest_parser.set_defaults(func=handle_ingest)

    process_parser = subparsers.add_parser("process", help="Ingerir e traduzir documento")
    process_parser.add_argument("--input", required=True, help="Caminho para o arquivo HTML")
    process_parser.add_argument(
        "--languages",
        default="en",
        help="Lista de idiomas alvo separada por vírgula",
    )
    process_parser.add_argument("--source-lang", default="pt", help="Código do idioma de origem")
    process_parser.add_argument("--device", default="auto", help="Dispositivo (auto|cuda|cpu)")
    process_parser.add_argument("--fp16", action="store_true", help="Ativar fp16 quando suportado")
    process_parser.add_argument(
        "--mode",
        choices=["node", "window", "doc", "doc-sintatico"],
        default="node",
        help=(
            "Estratégia: node (isolado), window (contexto local), doc (documento linearizado), "
            "doc-sintatico (documento com repartição sintática)."
        ),
    )
    process_parser.add_argument(
        "--backend",
        choices=["hf", "google"],
        default="hf",
        help="Backend: HuggingFace (hf) ou Google Gemini (google)",
    )
    process_parser.add_argument(
        "--rag-topk",
        type=int,
        default=0,
        help="Número de trechos a recuperar para contexto RAG (0 desativa)",
    )
    process_parser.add_argument(
        "--rag-build-index",
        action="store_true",
        help="Força reconstrução do índice RAG antes de processar",
    )
    process_parser.add_argument(
        "--force",
        action="store_true",
        help="Força combinações não recomendadas (ex.: backend google com modo diferente de doc)",
    )
    process_parser.add_argument(
        "--observe",
        action="store_true",
        help="Ativa modo observador e imprime eventos detalhados da tradução em tempo real",
    )
    process_parser.add_argument(
        "--observe-jsonl",
        help="Salva eventos de telemetria em arquivo JSONL (um evento por linha)",
    )
    process_parser.set_defaults(func=handle_process)

    export_parser = subparsers.add_parser("export", help="Exportar variante do HTML traduzido")
    export_parser.add_argument("--doc", required=True, help="Nome base do documento (sem sufixo de idioma)")
    export_parser.add_argument("--language", required=True, help="Código do idioma de destino")
    export_parser.add_argument(
        "--variant",
        choices=["baseline", "adapted", "human"],
        default="adapted",
        help="Variante para exportar",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Caminho de saída opcional",
    )
    export_parser.add_argument("--source-lang", default="pt", help="Código do idioma de origem")
    export_parser.set_defaults(func=handle_export)

    export_text_parser = subparsers.add_parser("export-text", help="Exportar texto traduzido (arquivo .txt)")
    export_text_parser.add_argument("--doc", required=True, help="Nome base do documento (sem sufixo de idioma)")
    export_text_parser.add_argument("--language", required=True, help="Código do idioma de destino")
    export_text_parser.add_argument(
        "--variant",
        choices=["baseline", "adapted", "human"],
        default="adapted",
        help="Variante para exportar",
    )
    export_text_parser.add_argument("--source-lang", default="pt", help="Código do idioma de origem")
    export_text_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Caminho de saída opcional (.txt)",
    )
    export_text_parser.set_defaults(func=handle_export_text)

    return parser.parse_args()


def build_pipeline_config(args: argparse.Namespace) -> PipelineConfig:
    """Monta a configuração de pipeline a partir dos argumentos da CLI.

    Responsável por:
    - Resolver caminhos do projeto, dados, banco, glossário e corpus.
    - Converter lista de idiomas alvo.
    - Preparar configurações de tradução (backend, estratégia) e RAG.
    """
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    if hasattr(args, "languages"):
        target_langs = _parse_languages(args.languages)
    elif hasattr(args, "language"):
        target_langs = [args.language]
    else:
        target_langs = ["en"]

    rag_index_dir = data_dir / "rag_index"
    paths = PathsConfig(
        project_root=project_root,
        data_dir=data_dir,
        db_path=data_dir / "db" / "nlp_tcc.sqlite",
        glossario_dir=project_root / "glossario",
        corpus_dir=project_root / "corpus",
        results_dir=project_root / "results",
    )
    config = PipelineConfig(
        translation=TranslationConfig(
            device=args.device if hasattr(args, "device") else "auto",
            fp16=bool(getattr(args, "fp16", False)),
            backend=getattr(args, "backend", "hf"),
            strategy=getattr(args, "mode", "node"),
        ),
        source_lang=args.source_lang,
        target_langs=target_langs,
        paths=paths,
        rag=RagConfig(
            top_k=getattr(args, "rag_topk", 0),
            max_context_chars=5000,
            index_dir=rag_index_dir,
            enabled=True,
        ),
    )
    return config


def _process_doc_level(
    nodes: List[dict],
    lang: str,
    doc_service: DocLevelTranslationService,
    node_repo: NodeRepository,
    logger,
) -> int:
    """Processa tradução em nível de documento inteiro (doc-level).

    Pipeline detalhado:
    1) Linearização: os nós são convertidos para uma sequência única com marcadores <N#>…</N#> preservando a ordem.
    2) (Opcional) RAG: o serviço pode recuperar trechos do glossário/corpus e injetar no prompt (LLM Google).
    3) Tradução: uma única chamada ao backend para o documento inteiro linearizado.
    4) Parse/Re-mapeamento: o texto traduzido é dividido por marcadores e mapeado de volta para IDs originais.
    5) Persistência: grava tradução de cada nó no SQLite.

    Vantagens: maior coerência global, melhor manutenção de contexto e terminologia.
    Nota: o modo doc-sintatico reutiliza este pipeline, mas com um serviço que reparte grupos curtos
    usando heurísticas sintáticas para evitar perdas de texto.
    """
    # Caso especial: se estivermos no backend Google e o RAG estiver ativado (top_k>0),
    # executamos duas passagens: (1) baseline SEM RAG, (2) adapted COM RAG.
    # Para outros cenários, preservamos o comportamento atual (uma única passagem gravando ambas colunas iguais).
    try:
        backend_name = getattr(doc_service.config.translation, "backend", "hf")
        rag_cfg = getattr(doc_service.config, "rag", None)
        rag_enabled = bool(rag_cfg and getattr(rag_cfg, "top_k", 0) > 0)
    except Exception:
        backend_name = "hf"
        rag_enabled = False

    if rag_enabled:
        # 1) Baseline sem RAG - criamos novos configs imutáveis com top_k=0
        from dataclasses import replace
        original_config = doc_service.config
        baseline_rag_config = replace(original_config.rag, top_k=0)
        baseline_pipeline_config = replace(original_config, rag=baseline_rag_config)
        doc_service.config = baseline_pipeline_config
        id_to_baseline = doc_service.translate_document(nodes, target_lang=lang)

        # 2) Adapted com RAG (restaura config original)
        doc_service.config = original_config
        id_to_adapted = doc_service.translate_document(nodes, target_lang=lang)
        context_payload = getattr(doc_service, "last_context", None)

        translated_count = 0
        for node in nodes:
            nid = node["id"]
            baseline_text = id_to_baseline.get(nid) or node.get("original_text", "")
            adapted_text = id_to_adapted.get(nid) or baseline_text
            # Persistência separada para permitir comparação real baseline vs adapted
            node_repo.save_baseline(node_id=nid, translation=baseline_text)
            node_repo.save_adapted(node_id=nid, translation=adapted_text, context=context_payload)
            translated_count += 1
        return translated_count

    # Caminho padrão (uma única passagem) — grava as duas colunas com o mesmo valor
    id_to_translation = doc_service.translate_document(nodes, target_lang=lang)
    context_payload = getattr(doc_service, "last_context", None)
    translated_count = 0
    for node in nodes:
        translated_text = id_to_translation.get(node["id"]) or node.get("original_text", "")
        node_repo.save_translation(node_id=node["id"], translation=translated_text, context=context_payload)
        translated_count += 1
    return translated_count


def _process_window_level(
    nodes: List[dict],
    lang: str,
    translation_service: TranslationService,
    node_repo: NodeRepository,
    logger,
) -> int:
    """Processa tradução em janelas de contexto local (window-level).

    Pipeline detalhado:
    1) Agrupamento: constrói janelas com nós vizinhos para prover contexto local.
    2) Tradução por janela: uma chamada por janela ao backend.
    3) Divisão: reparte o texto traduzido da janela de volta por nó na mesma ordem.
    4) Persistência: grava tradução de cada nó no SQLite.

    Observação: se algum nó não receber tradução devido a falha, cai no fallback
    traduzindo aquele nó isoladamente para não ficar sem resultado.
    """
    id_to_translation = translation_service.translate_nodes_windowed(nodes, target_lang=lang)
    translated_count = 0
    for node in nodes:
        translated_text = id_to_translation.get(node["id"]) or translation_service.translate_node(node, target_lang=lang)
        node_repo.save_translation(node_id=node["id"], translation=translated_text)
        translated_count += 1
    return translated_count


def _process_node_level(
    nodes: List[dict],
    lang: str,
    translation_service: TranslationService,
    node_repo: NodeRepository,
    logger,
) -> int:
    """Processa tradução nó-a-nó (node-level) isoladamente.

    Pipeline detalhado:
    1) Para cada nó: chama o backend com apenas o texto daquele nó (sem contexto adicional).
    2) Persistência: grava tradução de cada nó no SQLite.
    """
    translated_count = 0
    for node in nodes:
        with log_time(logger, f"translate node {node['node_path']} -> {lang}"):
            translated_text = translation_service.translate_node(node, target_lang=lang)
            node_repo.save_translation(node_id=node["id"], translation=translated_text)
            translated_count += 1
    return translated_count


def handle_ingest(args: argparse.Namespace) -> None:
    """Ingere um HTML, indexa nós e persiste no banco para os idiomas alvo.

    Saída:
    - Gera arquivo HTML indexado (com comentários/IDs) em data/extracted.
    - Cria entradas de documento e nós no banco SQLite.
    """
    config = build_pipeline_config(args)
    logger = get_logger()
    results = _ingest_internal(config, Path(args.input), logger)
    logger.info("Documento '%s' ingerido com %d nós", results["doc_name"], results["node_count"])


def handle_process(args: argparse.Namespace) -> None:
    """Executa a tradução conforme estratégia e backend escolhidos.

    Estratégias:
    - node: traduz nó a nó, mais simples, menos contexto.
    - window: agrupa nós em janelas (contexto local), traduz como bloco, e reparte por nó.
    - doc: lineariza o documento completo em blocos <N#>…</N#>, traduz em uma chamada e mapeia de volta.
    - doc-sintatico: mesma linearização do doc mas com heurísticas adicionais para repartir grupos curtos respeitando limites sintáticos.

        Sobre RAG (Retrieval-Augmented Generation): é uma técnica para injetar conhecimento externo
        ao modelo (glossário/corpus) no momento da geração/tradução. Aqui usamos RAG no modo doc
        para recuperar trechos relevantes e concatená-los como "contexto" no prompt do backend Google.

        - Como é usado normalmente: você representa consulta/documento e base de conhecimento em
            embeddings; recupera top_k trechos similares; injeta esses trechos no prompt (LLM) ou
            ajusta o decodificador (em modelos que suportam).
        - Neste projeto: a injeção é feita via prompt no backend Google (Gemini). O backend
            Hugging Face (seq2seq) não implementa ainda um mecanismo para consumir esse contexto;
            RAG aplicado a HF exigiria uma estratégia alternativa (ex.: pós-processamento guiado por
            glossário, substituição terminológica antes/depois, ou ajuste de prefixos/forçado de termos),
            o que não está implementado nesta versão para manter simplicidade e evitar risco de quebrar
            a linearização/segmentação.
    """
    config = build_pipeline_config(args)
    logger = get_logger()

    if args.backend == "google" and args.mode not in ("doc", "doc-sintatico"):
        aviso = (
            "Combinação backend=google e modo=%s não é recomendada: consumo elevado de tokens e prompt"
            " otimizado apenas para modo doc/doc-sintatico. Use --mode doc, --mode doc-sintatico ou acrescente --force "
            "para continuar mesmo assim." % args.mode
        )
        if not getattr(args, "force", False):
            raise SystemExit(aviso)
        logger.warning(aviso + " Prosseguindo porque --force foi fornecido.")
    # Opcional: reconstruir índice RAG antes de iniciar
    if getattr(args, "rag_build_index", False) and config.rag and config.paths:
        from src.rag.retriever import Retriever
        index_dir = config.rag.index_dir or (config.paths.data_dir / "rag_index")
        retriever = Retriever(model_name=config.rag.model, index_dir=index_dir, db_path=config.paths.db_path)
        retriever.build_index()
        logger.info("Índice RAG reconstruído em %s", index_dir)
    # Ingestão do HTML: cria (ou atualiza) no SQLite os registros de documento e nós.
    # Motivo: isso permite traduzir/reatribuir sem reindexar, além de exportar em fluxos distintos.
    ingest_result = _ingest_internal(config, Path(args.input), logger)
    db = Database(config.paths.db_path)
    node_repo = NodeRepository(db)
    # Novo serviço permite modos diferentes; parâmetro futuro via CLI.
    translation_service = TranslationService(config=config)
    translation_service.mode = args.mode
    doc_service: DocLevelTranslationService | None = None
    doc_sint_service: DocSyntacticTranslationService | None = None
    translations_per_lang: Dict[str, int] = {}
    observe_enabled = bool(getattr(args, "observe", False) or getattr(args, "observe_jsonl", None))
    jsonl_path = getattr(args, "observe_jsonl", None)
    doc_name = ingest_result.get("doc_name") if isinstance(ingest_result, dict) else None
    doc_name_value = doc_name if isinstance(doc_name, str) and doc_name else None
    doc_label = doc_name_value or "(sem nome)"
    with translation_observer(
        enabled=observe_enabled,
        config=config,
        mode=args.mode,
        backend=args.backend,
        doc_name=doc_name_value,
        target_langs=config.target_langs,
        jsonl_path=jsonl_path,
        console=bool(getattr(args, "observe", False)),
    ):
        for lang, document_id in ingest_result["document_ids"].items():
            nodes = node_repo.list_nodes(document_id)
            emit_language_start(
                observe_enabled,
                doc_name=doc_label,
                target_lang=lang,
                mode=args.mode,
                backend=args.backend,
                node_count=len(nodes),
            )
            if args.mode == "doc":
                if doc_service is None:
                    doc_service = DocLevelTranslationService(config=config)
                translated_count = _process_doc_level(nodes, lang, doc_service, node_repo, logger)
            elif args.mode == "doc-sintatico":
                if doc_sint_service is None:
                    doc_sint_service = DocSyntacticTranslationService(config=config)
                translated_count = _process_doc_level(nodes, lang, doc_sint_service, node_repo, logger)
            elif args.mode == "window":
                translated_count = _process_window_level(nodes, lang, translation_service, node_repo, logger)
            else:
                translated_count = _process_node_level(nodes, lang, translation_service, node_repo, logger)
            translations_per_lang[lang] = translated_count
            emit_language_finish(
                observe_enabled,
                doc_name=doc_label,
                target_lang=lang,
                translated_nodes=translated_count,
            )
    for lang, count in translations_per_lang.items():
        logger.info("Traduzidos %d nós para o idioma %s", count, lang)


def handle_export(args: argparse.Namespace) -> None:
    """Reconstrói um HTML com a variante de tradução desejada.

    Variantes:
    - baseline: texto original (ou baseline da máquina, conforme implementação do ExportService).
    - adapted: tradução produzida pelo pipeline (recomendada).
    - human: caminho para inserir uma versão humana (se existir no DB).
    """
    # Configuração e recursos principais
    config = build_pipeline_config(args)
    logger = get_logger()
    db = Database(config.paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)

    # Caminhos fixos usados neste método (agrupados no topo)
    extracted_dir = config.paths.data_dir / "extracted"
    html_path = extracted_dir / f"{args.doc}_indexed.html"  # HTML indexado criado em ingest/process
    default_output_path = config.paths.results_dir / "html" / f"{args.doc}_{args.variant}_{args.language}.html"
    output_path = args.output or default_output_path

    # Recupera ID do documento para idioma alvo
    document_id = doc_repo.find_document_id(args.doc, args.source_lang, args.language)
    if document_id is None:
        raise SystemExit(
            f"Documento {args.doc} ({args.source_lang}->{args.language}) não encontrado. Rode ingest/process antes."
        )
    nodes = node_repo.list_nodes(document_id)
    if not html_path.exists():
        raise SystemExit(f"HTML indexado não encontrado em {html_path}. Execute ingest/process novamente.")

    # HTML base + traduções por nó -> reconstrução
    original_html = read_html(html_path)
    export_service = ExportService()
    logger.info("Exportando variante %s para %s -> %s", args.variant, args.doc, args.language)
    export_service.export_variant(
        original_html=original_html,
        nodes=_inflate_nodes(nodes),
        variant=args.variant,
        output_path=output_path,
    )
    logger.info("Arquivo gerado em %s", output_path)


def handle_export_text(args: argparse.Namespace) -> None:
    """Gera um arquivo .txt com o conteúdo traduzido do documento.

    Útil para avaliação automática/humana (BLEU, comparações) ou leitura sequencial.
    """
    config = build_pipeline_config(args)
    logger = get_logger()
    db = Database(config.paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_id = doc_repo.find_document_id(args.doc, args.source_lang, args.language)
    if document_id is None:
        raise SystemExit(
            f"Documento {args.doc} ({args.source_lang}->{args.language}) não encontrado. Rode ingest/process antes."
        )
    nodes = node_repo.list_nodes(document_id)
    extracted_dir = config.paths.data_dir / "extracted"
    html_path = extracted_dir / f"{args.doc}_indexed.html"
    if not html_path.exists():
        raise SystemExit(f"HTML indexado não encontrado em {html_path}. Execute ingest/process novamente.")
    original_html = read_html(html_path)
    from src.services.text_export_service import TextExportService

    txt_service = TextExportService()
    output_path = args.output or (
        config.paths.results_dir / "text" / f"{args.doc}_{args.variant}_{args.language}.txt"
    )
    logger.info("Exportando texto (%s) para %s -> %s", args.variant, args.doc, args.language)
    txt_service.export_variant_text(
        original_html=original_html,
        nodes=_inflate_nodes(nodes),
        variant=args.variant,
        output_path=output_path,
    )
    logger.info("Arquivo gerado em %s", output_path)


def _ingest_internal(
    config: PipelineConfig, input_path: Path, logger
) -> Dict[str, object]:
    """Pipeline interno de ingestão usado por ingest e process.

    Passos:
    1) Lê o HTML de entrada.
    2) Indexa nós (DOM) e escreve um HTML indexado em data/extracted.
    3) Persiste documento e nós no banco, um por idioma alvo.
    Retorna metadados (nome e IDs por idioma) para a etapa seguinte.
    """
    html = read_html(input_path)
    indexed_html, nodes = index_html(html)
    extracted_dir = config.paths.data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    doc_name = input_path.stem
    indexed_path = extracted_dir / f"{doc_name}_indexed.html"
    write_html(indexed_path, indexed_html)
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    db = Database(config.paths.db_path)
    db.init_schema()
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_ids: Dict[str, int] = {}
    for target_lang in config.target_langs:
        document_id = doc_repo.upsert_document(
            name=doc_name,
            lang_src=config.source_lang,
            lang_tgt=target_lang,
            sha256=sha256,
        )
        node_repo.delete_nodes_by_document(document_id)
        node_repo.insert_nodes(document_id, nodes)
        document_ids[target_lang] = document_id
    return {
        "doc_name": doc_name,
        "indexed_path": indexed_path,
        "node_count": len(nodes),
        "document_ids": document_ids,
    }


def _inflate_nodes(rows: List[dict]) -> List[dict]:
    """Converte o campo 'placeholders' salvo como JSON em estrutura Python.

    Evita que strings JSON fiquem sem parsing ao reconstruirmos os nós para export.
    """
    inflated = []
    for row in rows:
        placeholders = row.get("placeholders")
        if isinstance(placeholders, str):
            placeholders = json.loads(placeholders)
        inflated.append({**row, "placeholders": placeholders})
    return inflated


def _parse_languages(raw: str) -> List[str]:
    """Normaliza a lista de idiomas alvo a partir de uma string separada por vírgulas."""
    return [lang.strip() for lang in raw.split(",") if lang.strip()]


if __name__ == "__main__":
    args = parse_args()
    args.func(args)
