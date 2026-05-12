#!/bin/bash
# 校园订餐系统 - 一键部署脚本
# 适用于阿里云 Linux / CentOS 系统
# 使用方法: bash deploy.sh

set -e

DOMAIN="sydroo.top"
APP_DIR="/opt/campus-food"
SERVICE_NAME="campus-food"

echo "======================================"
echo "  校园订餐系统 - 开始部署"
echo "======================================"

# 1. 更新系统
echo "[1/8] 更新系统包..."
yum update -y -q

# 2. 安装依赖
echo "[2/8] 安装依赖..."
yum install -y python3 python3-pip python3-venv nginx git curl wget unzip

# 3. 安装 certbot（HTTPS证书）
echo "[3/8] 安装 certbot..."
pip3 install certbot certbot-nginx -q

# 4. 创建应用目录
echo "[4/8] 创建应用目录..."
mkdir -p $APP_DIR
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/uploads

# 5. 配置 Nginx
echo "[5/8] 配置 Nginx..."
cat > /etc/nginx/conf.d/campus-food.conf << 'NGINX_CONF'
server {
    listen 80;
    server_name sydroo.top www.sydroo.top;

    # 管理后台静态文件
    location /admin {
        alias /opt/campus-food/admin;
        index login.html;
        try_files $uri $uri/ /admin/login.html;
    }

    # API 反向代理
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 上传文件
    location /uploads {
        alias /opt/campus-food/uploads;
    }

    # 默认重定向到管理后台
    location / {
        return 301 /admin/login.html;
    }
}
NGINX_CONF

# 6. 启动 Nginx
echo "[6/8] 启动 Nginx..."
systemctl enable nginx
systemctl restart nginx

# 7. 创建 systemd 服务
echo "[7/8] 创建后端服务..."
cat > /etc/systemd/system/campus-food.service << 'SERVICE_CONF'
[Unit]
Description=Campus Food Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/campus-food/backend
Environment="DATABASE_URL_OVERRIDE=sqlite:////opt/campus-food/data/campus_food.db"
Environment="WECHAT_PAY_MODE=mock"
ExecStart=/opt/campus-food/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/opt/campus-food/logs/backend.log
StandardError=append:/opt/campus-food/logs/backend-error.log

[Install]
WantedBy=multi-user.target
SERVICE_CONF

systemctl daemon-reload

echo "[8/8] 部署脚本准备完成！"
echo ""
echo "======================================"
echo "  下一步操作："
echo "======================================"
echo "1. 上传项目文件到 /opt/campus-food/backend"
echo "2. 上传管理后台到 /opt/campus-food/admin"
echo "3. 运行: cd /opt/campus-food/backend && python3 -m venv .venv"
echo "4. 运行: .venv/bin/pip install -r requirements.txt"
echo "5. 运行: .venv/bin/python scripts/init_db.py"
echo "6. 运行: systemctl start campus-food"
echo "7. 申请HTTPS证书: certbot --nginx -d sydroo.top -d www.sydroo.top"
echo ""
echo "后端日志: tail -f /opt/campus-food/logs/backend.log"
echo "======================================"
