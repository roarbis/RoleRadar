#!/usr/bin/env bash
# ── RoleRadar — Ubuntu VM Setup Script ──────────────────────────────────────
#
# Run as root (or with sudo) on a fresh Ubuntu 22.04 / 24.04 VM:
#   sudo bash setup.sh
#
# What it does:
#   1. Installs system packages (Python, Nginx, Docker optional)
#   2. Creates a dedicated 'roleradar' user
#   3. Clones the repo to /opt/roleradar
#   4. Creates a Python virtual environment and installs deps
#   5. Installs the systemd service
#   6. Configures Nginx as a reverse proxy
#   7. Opens firewall ports 80 and 443
# ---------------------------------------------------------------------------

set -euo pipefail

# ── Config — edit these ──────────────────────────────────────────────────────
REPO_URL="https://github.com/roarbis/RoleRadar.git"
APP_DIR="/opt/roleradar"
APP_USER="roleradar"
APP_PORT="8501"
DOMAIN=""     # leave empty for IP-only access; set to "yourdomain.com" for SSL
# ────────────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }

check_root() {
    [[ $EUID -eq 0 ]] || { echo "Please run with sudo."; exit 1; }
}

install_packages() {
    info "Updating package index..."
    apt-get update -qq

    info "Installing system packages..."
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        nginx \
        curl \
        libcurl4 \
        libxml2 \
        libxslt1.1 \
        ufw \
        ca-certificates \
        build-essential

    # Python 3.12 is default on Ubuntu 24.04; install it explicitly on 22.04
    python3 --version | grep -qE "3\.(11|12|13)" || {
        info "Installing Python 3.12 via deadsnakes PPA..."
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update -qq
        apt-get install -y python3.12 python3.12-venv python3.12-dev
    }

    PYTHON_BIN=$(command -v python3.12 || command -v python3)
    info "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version))"
}

create_user() {
    if id "$APP_USER" &>/dev/null; then
        info "User '$APP_USER' already exists — skipping."
    else
        info "Creating system user '$APP_USER'..."
        useradd --system --shell /bin/bash --home-dir "$APP_DIR" --create-home "$APP_USER"
    fi
}

clone_repo() {
    if [[ -d "$APP_DIR/.git" ]]; then
        info "Repo already cloned — pulling latest..."
        git -C "$APP_DIR" pull --ff-only
    else
        info "Cloning RoleRadar to $APP_DIR..."
        git clone "$REPO_URL" "$APP_DIR"
    fi
    chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
}

setup_venv() {
    info "Creating Python virtual environment..."
    PYTHON_BIN=$(command -v python3.12 || command -v python3)

    sudo -u "$APP_USER" bash -c "
        $PYTHON_BIN -m venv $APP_DIR/venv
        $APP_DIR/venv/bin/pip install --upgrade pip wheel
        $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt
    "
    info "Virtual environment ready."
}

create_data_dir() {
    info "Setting up data directory..."
    sudo -u "$APP_USER" mkdir -p "$APP_DIR/data/uploads"
    chmod 750 "$APP_DIR/data"
}

install_service() {
    info "Installing systemd service..."
    cp "$APP_DIR/deploy/roleradar.service" /etc/systemd/system/roleradar.service

    # Patch the service file with the correct Python bin
    PYTHON_BIN=$(command -v python3.12 || command -v python3)
    sed -i "s|/opt/roleradar/venv/bin/streamlit|$APP_DIR/venv/bin/streamlit|g" \
        /etc/systemd/system/roleradar.service

    systemctl daemon-reload
    systemctl enable roleradar
    systemctl start roleradar
    sleep 3
    systemctl is-active --quiet roleradar && info "Service is running." || \
        warning "Service failed to start — check: sudo journalctl -u roleradar -n 50"
}

configure_nginx() {
    info "Configuring Nginx..."

    if [[ -n "$DOMAIN" ]]; then
        NGINX_CONF="$APP_DIR/deploy/nginx-ssl.conf"
        sed "s/yourdomain.com/$DOMAIN/g" "$NGINX_CONF" \
            > /etc/nginx/sites-available/roleradar
        info "SSL config deployed for $DOMAIN"
        info "Run after setup: sudo certbot --nginx -d $DOMAIN"
    else
        cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/roleradar
    fi

    # Enable the site, remove default
    ln -sf /etc/nginx/sites-available/roleradar /etc/nginx/sites-enabled/roleradar
    rm -f /etc/nginx/sites-enabled/default

    nginx -t && systemctl reload nginx
    info "Nginx configured."
}

configure_firewall() {
    info "Configuring UFW firewall..."
    ufw --force enable
    ufw allow 22/tcp    comment "SSH"
    ufw allow 80/tcp    comment "HTTP"
    ufw allow 443/tcp   comment "HTTPS"
    # Block direct Streamlit port from outside (nginx proxies it)
    ufw deny "$APP_PORT/tcp" comment "Streamlit — internal only"
    ufw status verbose
}

print_summary() {
    echo ""
    echo "══════════════════════════════════════════════════════════"
    echo "  ✅  RoleRadar is installed and running!"
    echo "══════════════════════════════════════════════════════════"
    echo ""
    SERVER_IP=$(curl -s4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    if [[ -n "$DOMAIN" ]]; then
        echo "  App URL   : https://$DOMAIN"
        echo "  Next step : sudo certbot --nginx -d $DOMAIN"
    else
        echo "  App URL   : http://$SERVER_IP"
        echo "  Direct    : http://$SERVER_IP:$APP_PORT (internal)"
    fi
    echo ""
    echo "  Useful commands:"
    echo "    sudo systemctl status roleradar"
    echo "    sudo journalctl -u roleradar -f"
    echo "    cd $APP_DIR && git pull && sudo systemctl restart roleradar"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────
check_root
install_packages
create_user
clone_repo
setup_venv
create_data_dir
install_service
configure_nginx
configure_firewall
print_summary
