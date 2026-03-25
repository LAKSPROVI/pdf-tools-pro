# ─── Stage 1: Build ──────────────────────────────────────────────────────────
# Usamos uma imagem slim do Python 3.12 para manter a imagem final pequena.
# pikepdf exige libqpdf, então precisamos de algumas libs nativas.
FROM python:3.12-slim AS base

# Dependências nativas necessárias pelo pikepdf (libqpdf) e Pillow (libjpeg, zlib, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libqpdf-dev \
        libqpdf29 \
        libjpeg62-turbo \
        zlib1g \
        libfreetype6 \
        liblcms2-2 \
        libopenjp2-7 \
        libtiff6 \
        libwebp7 \
        libffi8 \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# ─── Stage 2: Instalar dependências Python ───────────────────────────────────
WORKDIR /app

# Copiar apenas o requirements para aproveitar cache do Docker
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ─── Stage 3: Copiar código da aplicação ─────────────────────────────────────
COPY backend.py .
COPY __init__.py .
COPY static/ ./static/

# Criar diretórios de dados temporários
# (na nuvem eles ficam em /tmp via variável PDF_TOOLS_DATA_DIR)
RUN mkdir -p /tmp/pdf_tools/uploads /tmp/pdf_tools/outputs

# ─── Configurações de ambiente ────────────────────────────────────────────────
ENV PORT=8000
ENV PDF_TOOLS_DATA_DIR=/tmp/pdf_tools
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expor a porta padrão (substituída pelo runtime da nuvem via $PORT)
EXPOSE 8000

# ─── Comando de inicialização ─────────────────────────────────────────────────
# Usamos sh -c para expandir a variável $PORT em tempo de execução
CMD ["sh", "-c", "uvicorn backend:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 300 --log-level info"]
