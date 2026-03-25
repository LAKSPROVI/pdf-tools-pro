"""
PDF Tools Backend - API FastAPI Robusta
Suporta PDFs de até 10.000 páginas e 500MB
Arquitetura de produção — pronta para nuvem (Docker / Railway / Render / Fly.io)
"""

import os
import io
import gc
import uuid
import time
import shutil
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

import aiofiles
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# ─── Configuração de logging (stdout-only para nuvem) ─────────────────────────
# Em nuvem, não gravamos em arquivo — apenas stdout/stderr (coletado pelo runtime)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("pdf_tools")

# ─── Diretórios ──────────────────────────────────────────────────────────────
# PDF_TOOLS_DATA_DIR permite sobrescrever via variável de ambiente.
# Padrão na nuvem: /tmp/pdf_tools  (filesystem efêmero é suficiente para arquivos temporários)
# Padrão local:    ./pdf_tools
_DATA_DIR = os.getenv("PDF_TOOLS_DATA_DIR", "/tmp/pdf_tools" if os.getenv("PORT") else "pdf_tools")
BASE_DIR   = Path(_DATA_DIR)
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

# Static files ficam sempre ao lado deste script — independente de onde o processo roda
STATIC_DIR = Path(__file__).parent / "static"

for d in [UPLOAD_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Configurações ────────────────────────────────────────────────────────────
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_PAGES = 10_000
CHUNK_SIZE = 8 * 1024 * 1024       # 8 MB chunks para upload
TEMP_FILE_TTL = 3600               # 1 hora para limpar arquivos temporários


# ─── Tarefa de limpeza automática ────────────────────────────────────────────
async def cleanup_old_files():
    """Remove arquivos temporários com mais de 1 hora"""
    while True:
        await asyncio.sleep(1800)  # A cada 30 minutos
        now = time.time()
        for directory in [UPLOAD_DIR, OUTPUT_DIR]:
            for f in directory.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) > TEMP_FILE_TTL:
                    try:
                        f.unlink()
                        logger.info(f"Arquivo temporário removido: {f.name}")
                    except Exception as e:
                        logger.warning(f"Erro ao remover {f.name}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(cleanup_old_files())
    logger.info("PDF Tools API iniciada com sucesso")
    yield
    logger.info("PDF Tools API encerrada")


# ─── App FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="PDF Tools API",
    description="Ferramenta robusta de processamento de PDF",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def gen_id() -> str:
    return uuid.uuid4().hex[:12]


async def save_upload(file: UploadFile, dest: Path) -> int:
    """Salva arquivo enviado em chunks, retorna tamanho em bytes"""
    total = 0
    async with aiofiles.open(dest, "wb") as out:
        while chunk := await file.read(CHUNK_SIZE):
            if total + len(chunk) > MAX_FILE_SIZE:
                raise HTTPException(413, "Arquivo excede o limite de 500 MB")
            await out.write(chunk)
            total += len(chunk)
    return total


def validate_pdf_path(path: Path) -> None:
    """Valida que o arquivo é um PDF real"""
    with open(path, "rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        raise HTTPException(400, "Arquivo não é um PDF válido")


def cleanup_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — COMPRESSÃO DE PDF
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/compress")
async def compress_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    level: str = Form("medium")  # low | medium | high
):
    """
    Comprime um PDF em 3 níveis:
    - low   : compressão suave, máxima qualidade (redução ~20%)
    - medium: balanceado (redução ~50%)
    - high  : máxima compressão (redução ~70-80%)
    """
    if level not in ("low", "medium", "high"):
        raise HTTPException(400, "Nível inválido. Use: low, medium, high")

    uid = gen_id()
    input_path = UPLOAD_DIR / f"{uid}_compress_in.pdf"
    output_path = OUTPUT_DIR / f"{uid}_compressed_{level}.pdf"

    try:
        await save_upload(file, input_path)
        validate_pdf_path(input_path)

        import pikepdf
        from PIL import Image

        logger.info(f"[{uid}] Comprimindo PDF nível={level}, arquivo={file.filename}")

        # Configurações por nível
        level_cfg = {
            "low":    {"image_quality": 90, "recompress_images": False},
            "medium": {"image_quality": 60, "recompress_images": True},
            "high":   {"image_quality": 30, "recompress_images": True},
        }
        cfg = level_cfg[level]

        with pikepdf.open(input_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages > MAX_PAGES:
                raise HTTPException(400, f"PDF tem {total_pages} páginas. Limite: {MAX_PAGES}")

            logger.info(f"[{uid}] Total de páginas: {total_pages}")

            # Configurações de compressão pikepdf
            compress_streams = True
            stream_decode_level = pikepdf.StreamDecodeLevel.generalized

            if cfg["recompress_images"]:
                # Recomprimir imagens página a página
                for i, page in enumerate(pdf.pages):
                    if i % 500 == 0 and i > 0:
                        logger.info(f"[{uid}] Processando página {i}/{total_pages}...")
                    try:
                        for name, obj in page.images.items():
                            img_obj = pikepdf.PdfImage(obj)
                            # Só recomprime se for grande o suficiente para valer
                            if obj.stream_data and len(obj.stream_data) > 10_000:
                                try:
                                    pil_img = img_obj.as_pil_image()
                                    buf = io.BytesIO()
                                    # Converter para RGB se necessário
                                    if pil_img.mode in ("RGBA", "P"):
                                        pil_img = pil_img.convert("RGB")
                                    pil_img.save(buf, format="JPEG",
                                                quality=cfg["image_quality"],
                                                optimize=True)
                                    buf.seek(0)
                                    obj.stream_data = buf.read()
                                    obj["/Filter"] = pikepdf.Name("/DCTDecode")
                                    for k in ["/DecodeParms", "/Predictor"]:
                                        if k in obj:
                                            del obj[k]
                                except Exception:
                                    pass  # Ignora imagens que não consegue processar
                    except Exception:
                        pass

            pdf.save(
                output_path,
                compress_streams=compress_streams,
                stream_decode_level=stream_decode_level,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                linearize=False
            )

        gc.collect()

        in_size = input_path.stat().st_size
        out_size = output_path.stat().st_size
        reduction = round((1 - out_size / in_size) * 100, 1) if in_size > 0 else 0

        logger.info(f"[{uid}] Compressão concluída: {in_size//1024}KB → {out_size//1024}KB ({reduction}%)")
        background_tasks.add_task(cleanup_file, input_path)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"comprimido_{level}_{file.filename}",
            background=BackgroundTasks(),
            headers={
                "X-Original-Size": str(in_size),
                "X-Compressed-Size": str(out_size),
                "X-Reduction-Percent": str(reduction),
                "X-Total-Pages": str(total_pages)
            }
        )

    except HTTPException:
        cleanup_file(input_path)
        raise
    except Exception as e:
        cleanup_file(input_path)
        cleanup_file(output_path)
        logger.error(f"[{uid}] Erro na compressão: {e}", exc_info=True)
        raise HTTPException(500, f"Erro ao comprimir PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 2 — IMAGEM → PDF
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/image-to-pdf")
async def image_to_pdf(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    page_size: str = Form("A4"),        # A4 | A3 | Letter | original
    orientation: str = Form("portrait") # portrait | landscape
):
    """
    Converte uma ou múltiplas imagens em PDF.
    Formatos suportados: JPG, PNG, BMP, GIF, TIFF, WEBP
    """
    if not files:
        raise HTTPException(400, "Nenhuma imagem enviada")
    if len(files) > 200:
        raise HTTPException(400, "Máximo de 200 imagens por vez")

    uid = gen_id()
    output_path = OUTPUT_DIR / f"{uid}_images_to.pdf"
    temp_files = []

    try:
        from PIL import Image
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, A3, letter, landscape

        # Mapa de tamanhos
        size_map = {
            "A4": A4, "A3": A3, "Letter": letter, "original": None
        }
        base_size = size_map.get(page_size, A4)
        if orientation == "landscape" and base_size:
            base_size = landscape(base_size)

        logger.info(f"[{uid}] Convertendo {len(files)} imagem(ns) para PDF")

        c = canvas.Canvas(str(output_path))

        for idx, upload in enumerate(files):
            img_path = UPLOAD_DIR / f"{uid}_img_{idx}_{upload.filename}"
            temp_files.append(img_path)

            file_bytes = await upload.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(413, f"Imagem {upload.filename} excede 500 MB")

            async with aiofiles.open(img_path, "wb") as f:
                await f.write(file_bytes)

            try:
                with Image.open(img_path) as pil_img:
                    # Converte para RGB (necessário para PDF)
                    if pil_img.mode in ("RGBA", "P", "LA"):
                        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                        if pil_img.mode == "P":
                            pil_img = pil_img.convert("RGBA")
                        if pil_img.mode in ("RGBA", "LA"):
                            bg.paste(pil_img, mask=pil_img.split()[-1])
                        else:
                            bg.paste(pil_img)
                        pil_img = bg
                    elif pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")

                    img_w, img_h = pil_img.size

                    if base_size is None:
                        # Usar tamanho original da imagem (em pontos, 72 dpi)
                        page_w = img_w * 72 / 96
                        page_h = img_h * 72 / 96
                    else:
                        page_w, page_h = base_size

                    c.setPageSize((page_w, page_h))

                    # Calcular escala mantendo proporção
                    scale = min(page_w / img_w, page_h / img_h)
                    draw_w = img_w * scale
                    draw_h = img_h * scale
                    x = (page_w - draw_w) / 2
                    y = (page_h - draw_h) / 2

                    # Salvar como JPEG temporário para reportlab
                    tmp_jpg = UPLOAD_DIR / f"{uid}_tmp_{idx}.jpg"
                    temp_files.append(tmp_jpg)
                    pil_img.save(tmp_jpg, "JPEG", quality=95)

                    c.drawImage(str(tmp_jpg), x, y, draw_w, draw_h)
                    c.showPage()

            except Exception as e:
                logger.warning(f"[{uid}] Erro ao processar imagem {upload.filename}: {e}")
                raise HTTPException(400, f"Erro ao processar imagem '{upload.filename}': {e}")

        c.save()
        gc.collect()

        out_size = output_path.stat().st_size
        logger.info(f"[{uid}] PDF gerado com {len(files)} página(s): {out_size//1024}KB")

        for f in temp_files:
            background_tasks.add_task(cleanup_file, f)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="imagens_convertidas.pdf",
            headers={"X-Total-Pages": str(len(files))}
        )

    except HTTPException:
        for f in temp_files:
            cleanup_file(f)
        raise
    except Exception as e:
        for f in temp_files:
            cleanup_file(f)
        cleanup_file(output_path)
        logger.error(f"[{uid}] Erro na conversão: {e}", exc_info=True)
        raise HTTPException(500, f"Erro ao converter imagens: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 3 — RECORTAR BORDAS DE PDF
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/crop-margins")
async def crop_margins(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    top: float = Form(0),
    bottom: float = Form(0),
    left: float = Form(0),
    right: float = Form(0),
    unit: str = Form("mm")  # mm | pt | cm | inch
):
    """
    Recorta bordas do PDF.
    Unidades: mm, pt, cm, inch
    Valores positivos = recortar; negativos = adicionar margem
    """
    uid = gen_id()
    input_path = UPLOAD_DIR / f"{uid}_crop_in.pdf"
    output_path = OUTPUT_DIR / f"{uid}_cropped.pdf"

    try:
        await save_upload(file, input_path)
        validate_pdf_path(input_path)

        import pikepdf
        from decimal import Decimal

        # Conversão para pontos PDF (1 pt = 1/72 polegada)
        unit_to_pt = {
            "mm": 72 / 25.4,
            "cm": 72 / 2.54,
            "inch": 72.0,
            "pt": 1.0
        }
        factor = unit_to_pt.get(unit, 72 / 25.4)

        top_pt    = top    * factor
        bottom_pt = bottom * factor
        left_pt   = left   * factor
        right_pt  = right  * factor

        logger.info(f"[{uid}] Recortando bordas: T={top}{unit} B={bottom}{unit} L={left}{unit} R={right}{unit}")

        with pikepdf.open(input_path) as pdf:
            total_pages = len(pdf.pages)
            if total_pages > MAX_PAGES:
                raise HTTPException(400, f"PDF tem {total_pages} páginas. Limite: {MAX_PAGES}")

            for i, page in enumerate(pdf.pages):
                # Pegar MediaBox atual
                if "/MediaBox" in page:
                    mb = page.MediaBox
                else:
                    mb = pikepdf.Array([0, 0, 595, 842])  # A4 padrão

                x0 = float(mb[0])
                y0 = float(mb[1])
                x1 = float(mb[2])
                y1 = float(mb[3])

                # Aplicar recorte
                new_x0 = x0 + left_pt
                new_y0 = y0 + bottom_pt
                new_x1 = x1 - right_pt
                new_y1 = y1 - top_pt

                # Verificar validade
                if new_x1 - new_x0 < 10 or new_y1 - new_y0 < 10:
                    raise HTTPException(400, f"Recorte muito agressivo na página {i+1}: dimensão resultante menor que 10pt")

                new_mb = pikepdf.Array([
                    Decimal(str(round(new_x0, 4))),
                    Decimal(str(round(new_y0, 4))),
                    Decimal(str(round(new_x1, 4))),
                    Decimal(str(round(new_y1, 4)))
                ])
                page.MediaBox = new_mb
                # Sincronizar CropBox com MediaBox
                if "/CropBox" in page:
                    page.CropBox = new_mb

            pdf.save(output_path, compress_streams=True)

        gc.collect()
        background_tasks.add_task(cleanup_file, input_path)

        logger.info(f"[{uid}] Recorte concluído: {total_pages} páginas")

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"recortado_{file.filename}",
            headers={"X-Total-Pages": str(total_pages)}
        )

    except HTTPException:
        cleanup_file(input_path)
        raise
    except Exception as e:
        cleanup_file(input_path)
        cleanup_file(output_path)
        logger.error(f"[{uid}] Erro no recorte: {e}", exc_info=True)
        raise HTTPException(500, f"Erro ao recortar PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 4 — JUNTAR PDFs
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/merge")
async def merge_pdfs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """
    Junta múltiplos PDFs em um único documento.
    Mantém a ordem dos arquivos enviados.
    Suporta PDFs grandes (até 500MB cada).
    """
    if len(files) < 2:
        raise HTTPException(400, "É necessário enviar pelo menos 2 PDFs para juntar")
    if len(files) > 50:
        raise HTTPException(400, "Máximo de 50 PDFs por vez")

    uid = gen_id()
    input_paths = []
    output_path = OUTPUT_DIR / f"{uid}_merged.pdf"

    try:
        import pikepdf

        total_pages_all = 0
        logger.info(f"[{uid}] Iniciando merge de {len(files)} PDFs")

        # Salvar todos os arquivos
        for idx, upload in enumerate(files):
            p = UPLOAD_DIR / f"{uid}_merge_{idx}_{upload.filename}"
            size = await save_upload(upload, p)
            validate_pdf_path(p)

            # Verificar páginas
            with pikepdf.open(p) as tmp:
                pages = len(tmp.pages)
                total_pages_all += pages
                logger.info(f"[{uid}] Arquivo {idx+1}: {upload.filename} ({pages} págs, {size//1024}KB)")

            if total_pages_all > MAX_PAGES:
                raise HTTPException(400, f"Total de páginas excede {MAX_PAGES}")

            input_paths.append(p)

        # Fazer merge em streaming (eficiente para arquivos grandes)
        with pikepdf.Pdf.new() as output_pdf:
            for idx, p in enumerate(input_paths):
                logger.info(f"[{uid}] Mesclando arquivo {idx+1}/{len(input_paths)}...")
                with pikepdf.open(p) as src:
                    output_pdf.pages.extend(src.pages)

            output_pdf.save(
                output_path,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate
            )

        gc.collect()

        out_size = output_path.stat().st_size
        logger.info(f"[{uid}] Merge concluído: {total_pages_all} páginas, {out_size//1024}KB")

        for p in input_paths:
            background_tasks.add_task(cleanup_file, p)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="documentos_unidos.pdf",
            headers={
                "X-Total-Pages": str(total_pages_all),
                "X-Files-Merged": str(len(files))
            }
        )

    except HTTPException:
        for p in input_paths:
            cleanup_file(p)
        raise
    except Exception as e:
        for p in input_paths:
            cleanup_file(p)
        cleanup_file(output_path)
        logger.error(f"[{uid}] Erro no merge: {e}", exc_info=True)
        raise HTTPException(500, f"Erro ao juntar PDFs: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT 5 — EXTRAIR PÁGINAS ESPECÍFICAS
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/extract-pages")
async def extract_pages(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pages: str = Form(...)  # "1,10,20,30" ou "1-5,10,15-20"
):
    """
    Extrai páginas específicas de um PDF.
    Exemplos de entrada:
    - "1,10,20,30"     → páginas 1, 10, 20, 30
    - "1-5,10,20-25"   → páginas 1 a 5, 10, 20 a 25
    - "1,3,5-10,50"    → combinações mistas
    Nota: Numeração começa em 1.
    """
    uid = gen_id()
    input_path = UPLOAD_DIR / f"{uid}_extract_in.pdf"
    output_path = OUTPUT_DIR / f"{uid}_extracted.pdf"

    try:
        await save_upload(file, input_path)
        validate_pdf_path(input_path)

        import pikepdf

        # ── Parse da string de páginas ──────────────────────────────────────
        page_numbers = set()
        parts = [p.strip() for p in pages.split(",") if p.strip()]

        for part in parts:
            if "-" in part:
                bounds = part.split("-")
                if len(bounds) != 2:
                    raise HTTPException(400, f"Faixa inválida: '{part}'")
                try:
                    start = int(bounds[0].strip())
                    end   = int(bounds[1].strip())
                    if start > end:
                        start, end = end, start
                    page_numbers.update(range(start, end + 1))
                except ValueError:
                    raise HTTPException(400, f"Número de página inválido: '{part}'")
            else:
                try:
                    page_numbers.add(int(part))
                except ValueError:
                    raise HTTPException(400, f"Número de página inválido: '{part}'")

        if not page_numbers:
            raise HTTPException(400, "Nenhuma página especificada")

        logger.info(f"[{uid}] Extraindo páginas: {sorted(page_numbers)}")

        with pikepdf.open(input_path) as src_pdf:
            total_pages = len(src_pdf.pages)
            if total_pages > MAX_PAGES:
                raise HTTPException(400, f"PDF tem {total_pages} páginas. Limite: {MAX_PAGES}")

            # Validar que as páginas existem
            invalid = [p for p in page_numbers if p < 1 or p > total_pages]
            if invalid:
                raise HTTPException(400, f"Páginas fora do intervalo (1-{total_pages}): {sorted(invalid)}")

            # Criar PDF com páginas selecionadas (em ordem)
            sorted_pages = sorted(page_numbers)

            with pikepdf.Pdf.new() as out_pdf:
                for pnum in sorted_pages:
                    out_pdf.pages.append(src_pdf.pages[pnum - 1])  # 0-indexed

                out_pdf.save(
                    output_path,
                    compress_streams=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate
                )

        gc.collect()

        out_size = output_path.stat().st_size
        logger.info(f"[{uid}] Extração concluída: {len(sorted_pages)} páginas de {total_pages}")
        background_tasks.add_task(cleanup_file, input_path)

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"paginas_extraidas_{file.filename}",
            headers={
                "X-Pages-Extracted": str(len(sorted_pages)),
                "X-Total-Original-Pages": str(total_pages),
                "X-Extracted-List": ",".join(str(p) for p in sorted_pages)
            }
        )

    except HTTPException:
        cleanup_file(input_path)
        raise
    except Exception as e:
        cleanup_file(input_path)
        cleanup_file(output_path)
        logger.error(f"[{uid}] Erro na extração: {e}", exc_info=True)
        raise HTTPException(500, f"Erro ao extrair páginas: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT AUXILIAR — INFORMAÇÕES DO PDF
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/info")
async def pdf_info(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Retorna informações sobre o PDF: páginas, tamanho, metadados"""
    uid = gen_id()
    input_path = UPLOAD_DIR / f"{uid}_info.pdf"

    try:
        size = await save_upload(file, input_path)
        validate_pdf_path(input_path)

        import pikepdf

        with pikepdf.open(input_path) as pdf:
            total_pages = len(pdf.pages)
            meta = {}
            try:
                with pdf.open_metadata() as m:
                    meta = {
                        "title": str(m.get("dc:title", "")),
                        "author": str(m.get("dc:creator", "")),
                        "created": str(m.get("xmp:CreateDate", "")),
                    }
            except Exception:
                pass

            # Dimensões da primeira página
            first_page = pdf.pages[0]
            if "/MediaBox" in first_page:
                mb = first_page.MediaBox
                page_w = round(float(mb[2]) - float(mb[0]), 1)
                page_h = round(float(mb[3]) - float(mb[1]), 1)
            else:
                page_w, page_h = 595, 842

        background_tasks.add_task(cleanup_file, input_path)

        return JSONResponse({
            "filename": file.filename,
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 2),
            "total_pages": total_pages,
            "page_width_pt": page_w,
            "page_height_pt": page_h,
            "page_width_mm": round(page_w * 25.4 / 72, 1),
            "page_height_mm": round(page_h * 25.4 / 72, 1),
            "metadata": meta
        })

    except HTTPException:
        cleanup_file(input_path)
        raise
    except Exception as e:
        cleanup_file(input_path)
        raise HTTPException(500, f"Erro ao ler informações do PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# SERVIR FRONTEND ESTÁTICO
# ═══════════════════════════════════════════════════════════════════════════════
# Servir arquivos estáticos apenas se o diretório existir (evita erro no boot)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning(f"Diretório de estáticos não encontrado: {STATIC_DIR}")


@app.get("/")
async def serve_frontend():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend não encontrado. Verifique se o diretório 'static/' existe.")
    return FileResponse(str(index))


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "max_file_mb": 500, "max_pages": MAX_PAGES}


if __name__ == "__main__":
    import uvicorn
    # A variável de ambiente PORT é usada por Railway, Render, Heroku, Fly.io, etc.
    port = int(os.getenv("PORT", 8765))
    uvicorn.run(
        "backend:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1,
        timeout_keep_alive=300,
        limit_max_requests=None,
        log_level="info"
    )
