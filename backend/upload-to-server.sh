#!/bin/bash
# 上传项目到服务器
# 在你的 Mac 上运行此脚本

SERVER="root@47.111.182.166"
APP_DIR="/opt/campus-food"

echo "上传后端代码..."
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='campus_food.db' \
  C:/Users/73143/campus-food-backend/ $SERVER:$APP_DIR/backend/

echo "上传管理后台..."
rsync -avz \
  C:/Users/73143/campus-food-admin/ $SERVER:$APP_DIR/admin/

echo "上传完成！"
