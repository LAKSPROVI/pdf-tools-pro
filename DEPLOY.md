# 🚀 DEPLOY NA NUVEM — PDF Tools Pro

Guia completo para colocar o PDF Tools Pro no ar em qualquer plataforma.

---

## 📁 Estrutura de arquivos de deploy

```
pdf-tools-pro/
├── Dockerfile                   ← Imagem Docker (Python + libqpdf + deps)
├── .dockerignore                ← Excluir arquivos desnecessários da imagem
├── docker-compose.yml           ← Teste local
│
├── setup-vps.sh                 ← ⭐ Setup automático em VPS Ubuntu/Debian
├── deploy.sh                    ← Redeploy/atualização na VPS
│
├── nginx/
│   └── pdf-tools-pro.conf      ← Configuração Nginx (proxy + HTTPS)
│
├── systemd/
│   └── pdf-tools-pro.service   ← Serviço systemd (auto-start)
│
├── Procfile                     ← Railway / Heroku
├── railway.toml                 ← Railway (Docker mode)
├── render.yaml                  ← Render.com
└── fly.toml                     ← Fly.io (São Paulo)
```

---

## 🖥️ VPS Própria (Recomendado para produção)

### Por que VPS?

| | VPS | Plataformas gratuitas |
|---|---|---|
| Limite de RAM | **Você escolhe** | 256–512 MB |
| Limite de upload | **520 MB** (configurado) | 50–100 MB na prática |
| Timeout de requisição | **300s** (configurado) | 30–60s |
| Custo | **$4–$14/mês** | $0 (mas com limitações sérias) |
| Dados persistentes | ✅ Sim | ❌ Filesystem efêmero |
| HTTPS | ✅ Let's Encrypt grátis | ✅ Incluído |

---

### ☁️ Provedores Recomendados

#### 🥇 Hetzner Cloud (melhor custo-benefício)
> **Mais barato da categoria com data centers na Europa**

| Plano | vCPU | RAM | SSD | Banda | Preço/mês |
|---|---|---|---|---|---|
| CX22 | 2 | **2 GB** | 40 GB | 20 TB | **~$4.49** |
| CX32 | 4 | **8 GB** | 80 GB | 20 TB | ~$9.49 |

- 🌍 Data centers: Nuremberg, Falkenstein, Helsinki, Ashburn (EUA), Singapura
- 👉 https://hetzner.com/cloud
- ⚠️ Aceita cartão de crédito internacional; pode ser mais lento do Brasil (latência ~180ms)

#### 🥈 DigitalOcean (mais simples de usar)
> **Interface muito fácil, boa documentação**

| Plano | vCPU | RAM | SSD | Banda | Preço/mês |
|---|---|---|---|---|---|
| Basic | 1 | **1 GB** | 25 GB | 1 TB | $6 |
| Basic | 2 | **2 GB** | 50 GB | 2 TB | **$12** |

- 🌍 Data center mais próximo: NYC (latência ~120ms do BR)
- 👉 https://digitalocean.com
- ✅ Aceita cartão, PayPal, boleto (via parceiro)

#### 🥉 Oracle Cloud Free Tier (FREE para sempre!)
> **2 VMs grátis com 1 GB de RAM cada — permanentemente**

| Plano | vCPU | RAM | SSD | Preço |
|---|---|---|---|---|
| VM.Standard.E2.1.Micro | 1 | **1 GB** | 47 GB | **GRÁTIS** |
| (2 instâncias) | 2 | **2 GB** total | 94 GB total | **GRÁTIS** |

- ⚠️ 1 GB de RAM pode ser insuficiente para PDFs muito grandes
- 🌍 Data center: Vinhedo, São Paulo (!) — **menor latência no Brasil**
- 👉 https://oracle.com/cloud/free/
- Requer cartão de crédito para verificação (não cobra)

#### 🇧🇷 AWS Lightsail / GCP / Azure (opções enterprise)
| Plano | RAM | Preço/mês |
|---|---|---|
| AWS Lightsail 2 GB | 2 GB | $10 |
| GCP e2-micro (free tier) | 1 GB | GRÁTIS (1 instância) |
| Azure B1s | 1 GB | ~$7 |

---

### 🚀 Setup Automático (caminho mais rápido)

**Requisito:** VPS com Ubuntu 22.04 ou 24.04 LTS (já criada e com acesso SSH)

#### Passo 1 — Preparar o repositório

Antes de rodar o setup, coloque o código no GitHub:

```bash
# Na sua máquina local, dentro da pasta pdf-tools-pro/
git init
git add .
git commit -m "chore: preparar deploy"
git remote add origin https://github.com/SEU_USUARIO/pdf-tools-pro.git
git push -u origin main
```

#### Passo 2 — Editar o script de setup

Abra `setup-vps.sh` e configure:

```bash
REPO_URL="https://github.com/SEU_USUARIO/pdf-tools-pro.git"  # ← Seu repositório
DOMAIN="pdftools.seudominio.com"  # ← Seu domínio (ou deixe vazio para usar só o IP)
```

#### Passo 3 — Rodar o setup na VPS

```bash
# Conectar na VPS via SSH
ssh root@IP_DA_SUA_VPS

# Baixar e executar o script de instalação
curl -fsSL https://raw.githubusercontent.com/SEU_USUARIO/pdf-tools-pro/main/setup-vps.sh | sudo bash

# OU: copiar via scp e executar
scp setup-vps.sh root@IP_DA_VPS:/tmp/
ssh root@IP_DA_VPS "sudo bash /tmp/setup-vps.sh"
```

O script automaticamente:
- ✅ Atualiza o sistema
- ✅ Instala Docker, Docker Compose, Nginx, Fail2ban, UFW
- ✅ Cria usuário `pdftools` dedicado
- ✅ Clona o repositório em `/opt/pdf-tools-pro`
- ✅ Faz o build da imagem Docker
- ✅ Configura Nginx como proxy reverso
- ✅ Abre portas 80/443/22 no firewall

---

### 🔒 Ativar HTTPS com Let's Encrypt

**Após** apontar o seu domínio para o IP da VPS (DNS A record), execute:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pdftools.seudominio.com

# Renovação automática já é configurada pelo certbot
# Para testar:
sudo certbot renew --dry-run
```

---

### 🔄 Atualizar a aplicação

```bash
# Na VPS:
cd /opt/pdf-tools-pro
sudo bash deploy.sh

# Para forçar rebuild da imagem sem cache:
sudo bash deploy.sh --no-cache
```

---

### 📋 Comandos de administração

```bash
# Ver logs em tempo real
docker logs -f pdf-tools-pro

# Status do container
docker compose -f /opt/pdf-tools-pro/docker-compose.prod.yml ps

# Reiniciar
docker compose -f /opt/pdf-tools-pro/docker-compose.prod.yml restart

# Parar
docker compose -f /opt/pdf-tools-pro/docker-compose.prod.yml down

# Verificar uso de recursos
docker stats pdf-tools-pro

# Verificar status do Nginx
sudo systemctl status nginx

# Verificar logs do Nginx
sudo tail -f /var/log/nginx/pdf-tools-error.log
```

---

## 🧪 Testar localmente com Docker (antes de subir)

```bash
# Na pasta pdf-tools-pro/
docker compose up --build

# Acesse: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Health: http://localhost:8000/health
```

---

## 📊 Requisitos de hardware recomendados por carga

| Uso esperado | RAM | vCPU | Plano recomendado |
|---|---|---|---|
| Uso pessoal / baixo | 1 GB | 1 | Oracle Free / Hetzner CX22 |
| Uso moderado (< 100 usuários/dia) | **2 GB** | 2 | **Hetzner CX22 ($4.49)** ✅ |
| Uso intenso (PDFs 500 MB frequentes) | 4–8 GB | 4 | Hetzner CX32 ($9.49) |
| Alta disponibilidade | 8+ GB | 4+ | DigitalOcean / AWS / load balancer |

---

## ⚠️ Considerações importantes

### Armazenamento temporário
Os arquivos processados ficam em `/tmp/pdf_tools` e são **automaticamente limpos a cada hora** (lógica no `backend.py`). Não é necessário armazenamento persistente.

### Segurança
- O script já configura **Fail2ban** (proteção contra brute force SSH)
- **UFW** limita acesso às portas necessárias
- Nginx tem **rate limiting** nos endpoints de upload (10 req/min por IP)
- Para mais segurança, considere adicionar autenticação HTTP básica no Nginx

### Uploads grandes
Para PDFs de 500 MB funcionar:
- Nginx configurado com `client_max_body_size 520m`
- `proxy_request_buffering off` (streaming direto, sem buffer em RAM)
- Timeouts de 300s em todos os estágios

---

## 🆘 Troubleshooting

### ❌ Container não sobe
```bash
docker logs pdf-tools-pro
# Verifique se a porta 8000 não está em uso: ss -tlnp | grep 8000
```

### ❌ Nginx retorna 502 Bad Gateway
```bash
# Verificar se o container está rodando
docker ps | grep pdf-tools
# Testar backend diretamente
curl http://localhost:8000/health
```

### ❌ Upload retorna 413 (arquivo muito grande)
```bash
# Verificar configuração do Nginx
grep client_max_body_size /etc/nginx/sites-available/pdf-tools-pro
```

### ❌ Timeout durante processamento de PDF grande
```bash
# Aumentar timeout no Nginx
# Editar /etc/nginx/sites-available/pdf-tools-pro
# proxy_read_timeout 600s;  # para PDFs muito grandes
sudo nginx -t && sudo systemctl reload nginx
```

### ❌ Erro de memória (OOM)
```bash
# Verificar memória disponível
free -h
# Ver se o container foi morto por OOM
dmesg | grep -i "oom\|killed"
# Solução: upgrade para VPS com mais RAM
```
