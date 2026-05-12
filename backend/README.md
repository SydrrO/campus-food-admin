# 校内订餐系统 - 后端API

FastAPI + MySQL + Redis 架构的校园订餐系统后端服务。

## 项目结构

```
campus-food-backend/
├── app/
│   ├── api/v1/          # API路由
│   ├── core/            # 核心配置
│   ├── db/              # 数据库连接
│   ├── models/          # SQLAlchemy模型
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # 业务逻辑
│   ├── utils/           # 工具函数
│   └── main.py          # 应用入口
├── requirements.txt     # 依赖清单
└── .env.example         # 环境变量示例
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
.venv\Scripts\python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

> 说明：当前开发机 Python 版本为 3.14，依赖已调整为较新的兼容区间版本。

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置
```

如需本地快速验证，可在 `.env` 中设置：

```bash
DATABASE_URL_OVERRIDE=sqlite:///./campus_food.db
```

设置后会跳过 MySQL，直接使用项目目录下的 SQLite 文件。

### 3. 初始化数据库

运行初始化脚本创建表并写入基础配置、分类和示例菜品：

```bash
.venv\Scripts\python scripts\init_db.py
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/health 检查服务状态。

如使用 SQLite，本地完整验证流程推荐：先执行 `scripts\init_db.py`，再依次登录、创建地址、下单。

如需启用自动超时关单，可确保 Redis 可用，并配置：

```bash
REDIS_TIMEOUT_SCAN_SECONDS=30
```

应用启动后会后台轮询 Redis 超时队列；也可手动执行：

```bash
.venv\Scripts\python scripts\close_timeout_orders.py
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 微信支付（小程序真实支付）

当前项目已同时支持两种支付模式：

- `WECHAT_PAY_MODE=mock`：本地模拟支付
- `WECHAT_PAY_MODE=real`：真实微信支付

### 真实支付必填环境变量

在 `.env` 中至少补齐以下配置：

```bash
WECHAT_PAY_MODE=real
WECHAT_APPID=你的小程序AppID
WECHAT_SECRET=你的小程序Secret
WECHAT_MCHID=微信支付商户号
WECHAT_API_V3_KEY=32位APIv3密钥
WECHAT_PAY_NOTIFY_URL=https://你的域名/api/v1/payment/notify
WECHAT_PAY_PRIVATE_KEY_PATH=./certs/apiclient_key.pem
WECHAT_PAY_MERCHANT_SERIAL_NO=商户证书序列号
WECHAT_PAY_PLATFORM_CERT_PATH=./certs/wechatpay_platform.pem
```

如不想通过文件路径读取，也可直接传入：

```bash
WECHAT_PAY_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
```

### 当前支付接口

- `POST /api/v1/payment/prepay`
  - 为前端返回小程序 `wx.requestPayment` 所需参数
- `POST /api/v1/payment/notify`
  - 微信支付真实回调地址
- `POST /api/v1/payment/notify/mock`
  - 本地 mock 支付回调，仅在 `mock` 模式下使用

### 前端支付链路

当前小程序前端已具备真实支付分支：

1. 前端提交订单
2. 订单详情页调用 `/payment/prepay`
3. 若返回 `mode=real`，前端调用 `wx.requestPayment`
4. 后端以微信支付回调 `/payment/notify` 作为最终支付成功依据

### 上线前注意事项

1. `notify_url` 必须为公网 HTTPS 地址
2. 微信支付商户号必须与小程序 AppID 绑定
3. 平台证书需要定期更新
4. 首次真实联调建议使用低金额内测订单
5. 不要以前端支付成功回调作为最终支付成功依据，应以后端回调验签成功后的订单状态为准

## 技术栈

- **FastAPI** - 现代高性能Web框架
- **SQLAlchemy** - ORM
- **MySQL** - 主数据库
- **Redis** - 缓存和订单超时处理
- **Pydantic** - 数据验证
- **JWT** - 认证授权
