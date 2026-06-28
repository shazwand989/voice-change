#!/usr/bin/env bash
# SSL setup script for transcriber.shazwan-danial.com
# Run as: sudo bash ssl-setup.sh
set -euo pipefail

DOMAIN="transcriber.shazwan-danial.com"
NGINX_CONF="/etc/nginx/sites-available/transcriber"
LETSENCRYPT_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

echo "=== SSL Setup for ${DOMAIN} ==="

# ── 1. Create certbot challenge directory ──
sudo mkdir -p /var/www/certbot/.well-known/acme-challenge
sudo chown -R www-data:www-data /var/www/certbot

# ── 2. Temporarily switch to HTTP-only so certbot can verify ──
echo ""
echo "[1/4] Switching Nginx to HTTP-only mode for verification..."

sudo tee "${NGINX_CONF}" > /dev/null <<'NGINXEOF'
# TEMP — HTTP only for certbot verification
server {
    listen 80;
    server_name transcriber.shazwan-danial.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 "Certbot verification active — back soon.";
        add_header Content-Type text/plain;
    }
}
NGINXEOF

sudo nginx -t && sudo systemctl reload nginx
echo "✓ Nginx switched to HTTP-only"

# ── 3. Obtain certificate ──
echo ""
echo "[2/4] Obtaining Let's Encrypt certificate..."
if sudo certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --non-interactive --agree-tos \
    --email admin@shazwan-danial.com \
    -d "${DOMAIN}" 2>&1; then
    echo "✓ Certificate obtained"
else
    echo "✗ Certbot failed. Check DNS points ${DOMAIN} to this server."
    exit 1
fi

# ── 4. Restore full HTTPS config ──
echo ""
echo "[3/4] Restoring full HTTPS Nginx config..."

sudo tee "${NGINX_CONF}" > /dev/null <<NGINXEOF
# ── HTTP → HTTPS redirect ────────────────────────────────────────────────────
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# ── HTTPS ────────────────────────────────────────────────────────────────────
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include              /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam          /etc/letsencrypt/ssl-dhparams.pem;

    # ── Security headers ──
    add_header X-Frame-Options           "SAMEORIGIN" always;
    add_header X-Content-Type-Options    "nosniff" always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;

    # ── Upload limit ──
    client_max_body_size 500M;

    # ── Static files ──
    location /static/ {
        alias /var/www/voice-change/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /var/www/voice-change/media/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # ── Proxy to Gunicorn ──
    location / {
        proxy_pass http://unix:/run/gunicorn/transcriber.sock;

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;

        proxy_http_version 1.1;
        proxy_set_header Upgrade    \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout      300s;
        proxy_connect_timeout   60s;
        proxy_send_timeout      300s;
    }

    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
NGINXEOF

sudo nginx -t && sudo systemctl reload nginx
echo "✓ Full HTTPS config restored"

# ── 5. Set up auto-renewal cron ──
echo ""
echo "[4/4] Setting up auto-renewal cron job..."
sudo tee /etc/cron.daily/certbot-renew > /dev/null <<'CRONEOF'
#!/bin/bash
certbot renew --quiet --post-hook "systemctl reload nginx"
CRONEOF
sudo chmod +x /etc/cron.daily/certbot-renew
echo "✓ Auto-renewal configured (runs daily)"

echo ""
echo "=== SSL setup complete! ==="
echo "  https://${DOMAIN}"
echo ""
echo "Restart Gunicorn now:"
echo "  sudo systemctl restart gunicorn-transcriber"
