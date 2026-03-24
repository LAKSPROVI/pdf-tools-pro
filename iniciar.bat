@echo off
chcp 65001 >nul
title PDF Tools Pro

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║          PDF TOOLS PRO — Iniciando Servidor          ║
echo  ║   Suporte: 500 MB  /  10.000 paginas por arquivo     ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Ir para o diretório raiz do projeto
cd /d "%~dp0.."

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

:: Instalar dependências silenciosamente
echo [1/4] Verificando dependencias...
pip install fastapi uvicorn python-multipart pypdf pikepdf Pillow reportlab aiofiles --quiet --no-warn-script-location 2>nul

:: Criar diretórios necessários
echo [2/4] Preparando diretorios...
if not exist "pdf_tools\uploads"  mkdir "pdf_tools\uploads"
if not exist "pdf_tools\outputs"  mkdir "pdf_tools\outputs"
if not exist "pdf_tools\static"   mkdir "pdf_tools\static"

echo [3/4] Iniciando servidor...
echo.
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Acesse: http://localhost:8765
echo   API:    http://localhost:8765/docs
echo   Parar:  Ctrl+C
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo [4/4] Abrindo navegador em 3 segundos...
timeout /t 3 /nobreak >nul
start "" "http://localhost:8765"

python -m uvicorn pdf_tools.backend:app --host 0.0.0.0 --port 8765 --timeout-keep-alive 300

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao iniciar. Verifique se a porta 8765 esta livre.
    pause
)
