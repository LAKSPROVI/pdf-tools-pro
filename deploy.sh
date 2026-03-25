#!/bin/bash
# =============================================================================
# deploy.sh — Atualizar/Reimplantar o PDF Tools Pro na VPS
# =============================================================================
# Uso: bash deploy.sh [--no-cache]
# =============================================================================

set -euo pipefail

APP_DIR="/opt/pdf-tools-pro"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'; BOLD='\033[1m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }

NO_CACHE=""
[[ "${1:-}" == "--no-cache" ]] && NO_CACHE="--no-cache"

echo -e "${BOLD}${CYAN}=== PDF Tools Pro — Redeploy ===${NC}"

# Ir para o diretório da aplicação
cd "$APP_DIR"

# Verificar se há repositório git
if [[ -d ".git" ]]; then
    info "Atualizando código do repositório..."
    git fetch origin
    git reset --hard origin/main
    success "Código atualizado"
else
    warn "Sem repositório Git — usando código local existente"
fi

# Reconstruir imagem
info "Reconstruindo imagem Docker ${NO_CACHE:+(sem cache)}..."
docker compose -f docker-compose.prod.yml build $NO_CACHE

# Reiniciar sem downtime (pull then restart)
info "Reiniciando container..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Aguardar health check
PORT=$(grep -oP 'PORT=\K[0-9]+' .env.production 2>/dev/null || echo "8000")
info "Verificando saúde da aplicação..."
for i in $(seq 1 20); do
    if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        success "Aplicação saudável ✅"
        break
    fi
    sleep 3
    if [[ $i -eq 20 ]]; then
        echo "❌ Health check falhou. Últimas linhas de log:"
        docker logs --tail=50 pdf-tools-pro
        exit 1
    fi
done

# Limpar imagens antigas
info "Limpando imagens Docker antigas..."
docker image prune -f > /dev/null 2>&1 || true

echo -e "\n${BOLD}${GREEN}✅ Deploy concluído com sucesso!${NC}"
docker compose -f docker-compose.prod.yml ps
