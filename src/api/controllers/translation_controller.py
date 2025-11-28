from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Dict, List

from datetime import datetime
from fastapi import HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse

from ..controllers.base_controller import BaseController
from ...core.config import PipelineConfig, TranslationConfig, PathsConfig, RagConfig
from ...services.doc_level_service import DocLevelTranslationService
from ..models.translation_models import QuickTranslateRequest

class TranslationController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Rotas no nível raiz com endpoints em português
        super().__init__(prefix="", tags=["traducao"])  # root-level routes
        self.paths = paths
        self.project_root = paths.project_root
        self.arqs_dir = self.project_root / "arquivos_juridicos"
        self.results_dir = paths.results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.translations: Dict[str, Dict[str, Path]] = {}
        r = self.router

        @r.get(
            "/documentos",
            response_model=List[str],
            summary="Listar documentos disponíveis",
            description="Lista arquivos HTML disponíveis em 'arquivos_juridicos' para tradução.",
        )
        def listar_documentos():
            if not self.arqs_dir.exists():
                return []
            return sorted([p.name for p in self.arqs_dir.glob("*.html")])

        @r.get(
            "/documentos/{nome}",
            response_class=HTMLResponse,
            summary="Obter conteúdo HTML de um documento",
            description="Retorna o HTML bruto do documento solicitado.",
        )
        def obter_documento(nome: str):
            doc_path = self.arqs_dir / nome
            if not doc_path.exists():
                raise HTTPException(status_code=404, detail="Documento não encontrado")
            return doc_path.read_text(encoding="utf-8")

        @r.post(
            "/documentos/upload",
            summary="Enviar novo HTML para processamento",
            description="Recebe um arquivo HTML e o salva em 'arquivos_juridicos'. Retorna metadados do arquivo salvo.",
        )
        async def upload_documento(arquivo: UploadFile = File(...), nome_alvo: str | None = Form(None)):
            if not arquivo.filename and not nome_alvo:
                raise HTTPException(status_code=400, detail="Nome de arquivo não informado")
            target_name = nome_alvo or arquivo.filename or "documento.html"
            if not target_name.lower().endswith(".html"):
                target_name = f"{target_name}.html"
            safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(target_name).name)
            data = await arquivo.read()
            if not data:
                raise HTTPException(status_code=400, detail="Arquivo vazio")
            self.arqs_dir.mkdir(parents=True, exist_ok=True)
            dest_path = self.arqs_dir / safe_name
            dest_path.write_bytes(data)
            return {
                "nome": dest_path.name,
                "bytes": len(data),
                "caminho": str(dest_path),
            }

        @r.get(
            "/documentos/{nome}/variantes",
            summary="Listar variantes exportadas de um documento",
            description=(
                "Verifica a pasta de resultados e retorna as variantes disponíveis (baseline/adapted/human) "
                "para o documento e idioma informados."
            ),
        )
        def listar_variantes(nome: str, idioma: str = "en"):
            html_dir = self.results_dir / "html"
            nomeSemExtensao = Path(nome).stem
            print(f"Procurando variantes em: {html_dir}")
            variantes = []
            for variante in ("baseline", "adapted", "human"):
                candidate = html_dir / f"{nomeSemExtensao}_{variante}_{idioma}.html"
                print(f"Verificando existência de: {candidate}")
                if candidate.exists():
                    print(f"Encontrada variante: {candidate}")
                    stats = candidate.stat()
                    variantes.append(
                        {
                            "variante": variante,
                            "filename": candidate.name,
                            "idioma": idioma,
                            "size_bytes": stats.st_size,
                            "updated_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            "path": str(candidate),
                        }
                    )
            return {
                "documento": nome,
                "idioma": idioma,
                "variantes": variantes,
            }

        @r.post(
            "/traduzir",
            summary="Traduzir documento (baseline e adaptada)",
            description=(
                "Executa tradução no nível de documento. Retorna um ID de tradução e gera arquivos HTML "
                "para variantes baseline e adaptada. Use '/traducoes/{id}/{variante}' para visualizar."
            ),
        )
        def traduzir(payload: QuickTranslateRequest):
            doc_name = payload.document
            src_path = self.arqs_dir / doc_name
            if not src_path.exists():
                raise HTTPException(status_code=404, detail="Documento não encontrado")
            original_html = src_path.read_text(encoding="utf-8")
            nodes = self._extract_nodes_simple(original_html)
            if not nodes:
                raise HTTPException(status_code=400, detail="Falha na extração de nós (heurística)")

            cfg_base = PipelineConfig(
                translation=TranslationConfig(backend=payload.backend, strategy="doc"),
                paths=self.paths,
                source_lang="pt",
                target_langs=[payload.target_lang],
                rag=None,
            )
            svc_base = DocLevelTranslationService(cfg_base)
            trans_base = svc_base.translate_document(nodes, target_lang=payload.target_lang)

            rag_cfg = None
            if payload.rag_topk > 0:
                rag_cfg = RagConfig(top_k=payload.rag_topk, index_dir=self.paths.data_dir / "rag_index", enabled=True)
            cfg_adapt = PipelineConfig(
                translation=TranslationConfig(backend=payload.backend, strategy="doc"),
                paths=self.paths,
                source_lang="pt",
                target_langs=[payload.target_lang],
                rag=rag_cfg,
            )
            svc_adapt = DocLevelTranslationService(cfg_adapt)
            trans_adapt = svc_adapt.translate_document(nodes, target_lang=payload.target_lang)

            trans_id = uuid.uuid4().hex[:12]
            base_path = self.results_dir / f"translation_{trans_id}_baseline.html"
            adapt_path = self.results_dir / f"translation_{trans_id}_adapted.html"
            self._write_result_html(base_path, original_html, trans_base, mode="baseline")
            self._write_result_html(adapt_path, original_html, trans_adapt, mode="adaptada")
            self.translations[trans_id] = {"baseline": base_path, "adapted": adapt_path}

            return {
                "id_traducao": trans_id,
                "documento": doc_name,
                "idioma_destino": payload.target_lang,
                "backend": payload.backend,
                "rag_topk": payload.rag_topk,
                "variantes": ["baseline", "adapted"],
            }

        @r.get(
            "/traducoes/{id_traducao}/{variante}",
            summary="Visualizar HTML de uma variante de tradução",
            description="Retorna o HTML gerado para a variante informada (baseline ou adapted).",
        )
        def obter_traducao_variante(id_traducao: str, variante: str):
            meta = self.translations.get(id_traducao)
            if not meta or variante not in meta:
                raise HTTPException(status_code=404, detail="Variante não encontrada")
            return HTMLResponse(meta[variante].read_text(encoding="utf-8"))

        @r.get(
            "/traducoes/{id_traducao}/{variante}/download",
            summary="Baixar HTML de uma variante de tradução",
            description="Faz o download do arquivo HTML da variante especificada (baseline ou adapted).",
        )
        def baixar_traducao_variante(id_traducao: str, variante: str):
            meta = self.translations.get(id_traducao)
            if not meta or variante not in meta:
                raise HTTPException(status_code=404, detail="Variante não encontrada")
            return FileResponse(meta[variante], media_type="text/html", filename=meta[variante].name)

        @r.get(
            "/resultados/html/{filename}",
            summary="Obter HTML de resultado",
            description="Retorna o conteúdo de um arquivo HTML gerado na pasta de resultados.",
        )
        def obter_resultado_html(filename: str):
            file_path = self.results_dir / "html" / filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Arquivo não encontrado")
            return HTMLResponse(file_path.read_text(encoding="utf-8"))

    @staticmethod
    def _extract_nodes_simple(html_text: str) -> List[dict]:
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html_text, flags=re.IGNORECASE | re.DOTALL)
        out: List[dict] = []
        if paragraphs:
            for i, raw in enumerate(paragraphs):
                txt = re.sub(r"<[^>]+>", "", raw).strip()
                if txt:
                    out.append({"id": i, "original_text": txt})
        else:
            for i, line in enumerate(html_text.splitlines()):
                txt = re.sub(r"<[^>]+>", "", line).strip()
                if txt:
                    out.append({"id": i, "original_text": txt})
        return out

    @staticmethod
    def _write_result_html(path: Path, original_html: str, translated_nodes: Dict[int, str], mode: str) -> None:
        lines = ["<!doctype html>", "<html><head><meta charset='utf-8'><title>Resultado Tradução</title>",
                 "<style>body{font:14px system-ui;padding:16px;background:#f8fafc;color:#0f172a;}table{border-collapse:collapse;width:100%;}td,th{border:1px solid #cbd5e1;padding:6px;vertical-align:top;}th{background:#e2e8f0;}code{background:#e2e8f0;padding:2px 4px;border-radius:4px;}</style>",
                 f"</head><body><h1>Tradução {mode}</h1>"]
        lines.append("<table><thead><tr><th>ID Nó</th><th>Original</th><th>Traduzido</th></tr></thead><tbody>")
        nodes = TranslationController._extract_nodes_simple(original_html)
        for n in nodes:
            nid = n["id"]
            orig = n["original_text"].replace("<", "&lt;").replace(">", "&gt;")
            trad = translated_nodes.get(nid, "").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"<tr><td><code>{nid}</code></td><td>{orig}</td><td>{trad}</td></tr>")
        lines.append("</tbody></table></body></html>")
        path.write_text("\n".join(lines), encoding="utf-8")
