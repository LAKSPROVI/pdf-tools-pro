#!/bin/bash
# =============================================================================
# setup-vps.sh — Instalação completa do PDF Tools Pro em VPS Ubuntu/Debian
# =============================================================================
# Uso:
#   1. Copie este arquivo para a VPS (ou clone o repositório)
#   2. Execute: sudo bash setup-vps.sh
#   3. Siga as instruções ao final
#
# Testado em: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS / Debian 12
# =============================================================================

set -euo pipefail

# ─── Cores para output ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERRO]${NC}  $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}══ $* ══${NC}"; }

# ─── Verificar root ──────────────────────────────────────────────────────────
[[ "$EUID" -ne 0 ]] && error "Execute como root: sudo bash $0"

# ─── Detectar SO ─────────────────────────────────────────────────────────────
if ! command -v apt-get &>/dev/null; then
    error "Este script requer Ubuntu ou Debian (apt-get não encontrado)"
fi

# ─── Configurações (edite conforme necessário) ────────────────────────────────
APP_USER="pdftools"
APP_DIR="/opt/pdf-tools-pro"
APP_PORT="8000"                     # porta interna (Nginx fará proxy)
REPO_URL="https://github.com/SEU_USUARIO/pdf-tools-pro.git"  # ← EDITE AQUI
DOMAIN=""                           # Ex: "pdftools.seudominio.com" — deixe vazio para pular HTTPS

# ─── Banner ───────────────────────────────────────────────────────────────────
echo -e "
${BOLD}${BLUE}
╔══════════════════════════════════════════════════════════════╗
║          PDF Tools Pro — Setup Automático VPS                ║
║          Ubuntu/Debian + Docker + Nginx + HTTPS              ║
╚══════════════════════════════════════════════════════════════╝
${NC}"

# ─── Passo 1: Atualizar sistema ───────────────────────────────────────────────
step "1/8 Atualizando sistema"
apt-get update -qq
apt-get upgrade -y -qq
success "Sistema atualizado"

# ─── Passo 2: Instalar dependências base ─────────────────────────────────────
step "2/8 Instalando dependências base"
apt-get install -y -qq \
    curl wget git unzip ufw fail2ban \
    ca-certificates gnupg lsb-release \
    htop ncdu tmux nano
success "Dependências instaladas"

# ─── Passo 3: Instalar Docker ─────────────────────────────────────────────────
step "3/8 Instalando Docker"
if command -v docker &>/dev/null; then
    warn "Docker já instalado: $(docker --version)"
else
    # Método oficial Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Tentar Ubuntu; se falhar, tentar Debian
    DISTRO_ID=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/${DISTRO_ID}/linux/${DISTRO_ID} \
$(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

    systemctl enable docker
    systemctl start docker
    success "Docker instalado: $(docker --version)"
fi

# ─── Passo 4: Instalar Nginx ──────────────────────────────────────────────────
step "4/8 Instalando Nginx"
if command -v nginx &>/dev/null; then
    warn "Nginx já instalado: $(nginx -v 2>&1)"
else
    apt-get install -y -qq nginx
    systemctl enable nginx
    success "Nginx instalado"
fi

# ─── Passo 5: Criar usuário da aplicação ─────────────────────────────────────
step "5/8 Configurando usuário '$APP_USER'"
if id "$APP_USER" &>/dev/null; then
    warn "Usuário '$APP_USER' já existe"
else
    useradd -r -m -s /bin/bash "$APP_USER"
    usermod -aG docker "$APP_USER"
    success "Usuário '$APP_USER' criado e adicionado ao grupo docker"
fi

# ─── Passo 6: Clonar / atualizar repositório ─────────────────────────────────
step "6/8 Configurando aplicação em $APP_DIR"
if [[ "$REPO_URL" == *"SEU_USUARIO"* ]]; then
    warn "REPO_URL não configurado. Copiando arquivos do diretório atual..."
    mkdir -p "$APP_DIR"
    # Copiar arquivos do diretório onde o script está sendo executado
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "$SCRIPT_DIR"/. "$APP_DIR"/
else
    if [[ -d "$APP_DIR/.git" ]]; then
        info "Atualizando repositório existente..."
        cd "$APP_DIR" && git pull origin main
    else
        git clone "$REPO_URL" "$APP_DIR"
    fi
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
success "Aplicação configurada em $APP_DIR"

# ─── Passo 7: Build e start com Docker Compose ───────────────────────────────
step "7/8 Construindo e iniciando container"

# Criar .env de produção se não existir
ENV_FILE="$APP_DIR/.env.production"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" <<EOF
PORT=${APP_PORT}
PDF_TOOLS_DATA_DIR=/tmp/pdf_tools
PYTHONUNBUFFERED=1
EOF
    success "Arquivo $ENV_FILE criado"
fi

# Criar docker-compose de produção com as variáveis corretas
cat > "$APP_DIR/docker-compose.prod.yml" <<EOF
version: "3.9"

services:
  pdf-tools:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: pdf-tools-pro
    restart: always
    ports:
      - "127.0.0.1:${APP_PORT}:${APP_PORT}"
    env_file:
      - .env.production
    volumes:
      - pdf_data:/tmp/pdf_tools
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:${APP_PORT}/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  pdf_data:
    driver: local
EOF

cd "$APP_DIR"
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d

# Aguardar health check
info "Aguardando aplicação inicializar..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${APP_PORT}/health" > /dev/null 2>&1; then
        success "Aplicação respondendo em http://localhost:${APP_PORT}"
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        error "Aplicação não iniciou após 60s. Verifique: docker logs pdf-tools-pro"
    fi
done

# ─── Passo 8: Configurar Nginx ────────────────────────────────────────────────
step "8/8 Configurando Nginx"

NGINX_CONF="/etc/nginx/sites-available/pdf-tools-pro"

if [[ -n "$DOMAIN" ]]; then
    # Com domínio (configuração para HTTPS posterior)
    cat > "$NGINX_CONF" <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    # Limite de upload: 520 MB (um pouco acima do limite da app de 500 MB)
    client_max_body_size 520m;
    client_body_timeout  300s;

    # Timeouts para processamentos longos
    proxy_read_timeout   300s;
    proxy_send_timeout   300s;
    proxy_connect_timeout 10s;

    location / {
        proxy_pass         http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;

        # Buffers para arquivos grandes
        proxy_buffering          off;
        proxy_request_buffering  off;
    }

    # Gzip para assets estáticos
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;
}
NGINX
else
    # Sem domínio — acessível pelo IP do servidor
    PUBLIC_IP=$(curl -4 -sf https://api.ipify.org || echo "SEU_IP")
    cat > "$NGINX_CONF" <<NGINX
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    # Limite de upload: 520 MB
    client_max_body_size 520m;
    client_body_timeout  300s;
    proxy_read_timeout   300s;
    proxy_send_timeout   300s;
    proxy_connect_timeout 10s;

    location / {
        proxy_pass         http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_buffering          off;
        proxy_request_buffering  off;
    }
}
NGINX
fi

# Ativar site
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/pdf-tools-pro
# Remover default do nginx se existir
rm -f /etc/nginx/sites-enabled/default

# Testar e recarregar Nginx
nginx -t && systemctl reload nginx
success "Nginx configurado e recarregado"

# ─── Firewall ────────────────────────────────────────────────────────────────
step "Configurando Firewall (UFW)"
ufw --force enable
ufw allow ssh
ufw allow http
ufw allow https
ufw status
success "Firewall configurado"

# ─── Fail2ban ────────────────────────────────────────────────────────────────
step "Configurando Fail2ban (proteção contra brute force)"
systemctl enable fail2ban
systemctl start fail2ban
success "Fail2ban ativo"

# ─── Criar script de atualização ─────────────────────────────────────────────
cat > /usr/local/bin/pdf-tools-update <<'SCRIPT'
#!/bin/bash
set -euo pipefail
APP_DIR="/opt/pdf-tools-pro"
echo "=== Atualizando PDF Tools Pro ==="
cd "$APP_DIR"
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
echo "=== Atualização concluída ==="
docker compose -f docker-compose.prod.yml ps
SCRIPT
chmod +x /usr/local/bin/pdf-tools-update

# ─── Resumo final ─────────────────────────────────────────────────────────────
PUBLIC_IP=$(curl -4 -sf https://api.ipify.org 2>/dev/null || echo "SEU_IP_PUBLICO")

echo -e "
${BOLD}${GREEN}
╔══════════════════════════════════════════════════════════════╗
║                  ✅ INSTALAÇÃO CONCLUÍDA!                    ║
╚══════════════════════════════════════════════════════════════╝
${NC}
${BOLD}🌐 Acesso:${NC}
   http://${PUBLIC_IP}         ← IP público do servidor
   http://${PUBLIC_IP}/docs    ← Documentação da API
   http://${PUBLIC_IP}/health  ← Health check

${BOLD}📋 Comandos úteis:${NC}
   Ver logs:        docker logs -f pdf-tools-pro
   Status:          docker compose -f ${APP_DIR}/docker-compose.prod.yml ps
   Reiniciar:       docker compose -f ${APP_DIR}/docker-compose.prod.yml restart
   Atualizar:       pdf-tools-update
   Parar:           docker compose -f ${APP_DIR}/docker-compose.prod.yml down
"

if [[ -n "$DOMAIN" ]]; then
    echo -e "${BOLD}🔒 Para ativar HTTPS com Let's Encrypt:${NC}
   apt-get install -y certbot python3-certbot-nginx
   certbot --nginx -d ${DOMAIN}
   # O Certbot configura HTTPS e renovação automática
"
else
    echo -e "${YELLOW}⚠️  Para usar HTTPS, aponte um domínio para este IP (${PUBLIC_IP})
   e execute novamente com a variável DOMAIN configurada no script.${NC}
"
fi
