# 📄 PDF Tools Pro

Ferramenta web completa de processamento de PDF. Roda 100% localmente.

## ✅ Funcionalidades

| Ferramenta | Descrição |
|---|---|
| ⚡ **Compressão** | 3 níveis: Leve (~20%), Médio (~50%), Máximo (~70-80%) |
| 🖼️ **Imagem → PDF** | JPG, PNG, BMP, GIF, TIFF, WEBP → PDF. Múltiplas imagens = múltiplas páginas |
| ✂️ **Recortar Bordas** | Remove margens em mm/cm/pt/polegadas de todas as páginas |
| 🔗 **Juntar PDFs** | Une até 50 PDFs em um único documento (arraste para reordenar) |
| 📑 **Extrair Páginas** | Extrai páginas específicas: `1,10,20,30` ou faixas `1-5,10,15-20` |

## 🚀 Como usar

### Opção 1 — Duplo clique
Dê duplo clique em `pdf_tools/iniciar.bat`

### Opção 2 — Terminal
```bash
python -m uvicorn pdf_tools.backend:app --host 0.0.0.0 --port 8765
```

Acesse: **http://localhost:8765**

## 📋 Capacidades técnicas

- ✅ PDFs até **500 MB**
- ✅ PDFs até **10.000 páginas**
- ✅ Upload em chunks de 8 MB (sem timeout)
- ✅ Limpeza automática de arquivos temporários (1h)
- ✅ API REST completa (`/docs` para documentação)
- ✅ Processamento assíncrono

## 🔌 Endpoints da API

```
GET  /health                → Status do servidor
POST /api/info              → Informações do PDF
POST /api/compress          → Comprimir PDF
POST /api/image-to-pdf      → Imagens → PDF
POST /api/crop-margins      → Recortar bordas
POST /api/merge             → Juntar PDFs
POST /api/extract-pages     → Extrair páginas
```

## 📁 Estrutura

```
pdf_tools/
├── backend.py      ← API FastAPI (todos os processamentos)
├── __init__.py
├── iniciar.bat     ← Script de inicialização Windows
├── static/
│   └── index.html  ← Interface web completa
├── uploads/        ← Arquivos temporários (auto-limpos)
└── outputs/        ← PDFs processados (auto-limpos)
```

## 📦 Dependências

```
fastapi, uvicorn, python-multipart
pikepdf    ← processamento PDF de alto desempenho
pypdf      ← leitura de PDF
Pillow     ← processamento de imagens
reportlab  ← geração de PDF
aiofiles   ← I/O assíncrono
```
