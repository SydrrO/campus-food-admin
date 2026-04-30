# 微信支付真实接入上线清单

## 当前项目状态

项目已具备：

- 小程序前端 `wx.requestPayment` 调起能力
- 后端 `/api/v1/payment/prepay` 真实 JSAPI 下单能力
- 后端 `/api/v1/payment/notify` 微信支付回调验签与解密能力
- mock / real 双模式切换

当前唯一阻塞项为：**真实商户配置与证书文件尚未填入运行环境**。

---

## 一、上线前必须准备

### 小程序侧

- 小程序 AppID
- 小程序 Secret
- 小程序已开通微信支付能力

### 商户侧

- 微信支付商户号 `mchid`
- API v3 Key（32位）
- 商户私钥 `apiclient_key.pem`
- 商户证书序列号
- 微信支付平台证书 `wechatpay_platform.pem`（可选，如果改用微信支付公钥模式则不是必须）
- 微信支付公钥 `wechatpay_public.pem`（推荐）
- 微信支付公钥ID（推荐）

### 服务端侧

- HTTPS 公网域名
- 回调地址：`https://你的域名/api/v1/payment/notify`
- 放置证书目录：`./certs/`

---

## 二、文件准备

复制环境变量模板：

```bash
cp .env.real.example .env
```

将以下文件放入 `certs/`：

- `apiclient_key.pem`
- `wechatpay_platform.pem`（平台证书模式）
- `wechatpay_public.pem`（公钥模式，推荐）

---

## 三、关键环境变量

至少补齐：

```bash
WECHAT_PAY_MODE=real
WECHAT_APPID=
WECHAT_SECRET=
WECHAT_MCHID=
WECHAT_API_V3_KEY=
WECHAT_PAY_NOTIFY_URL=
WECHAT_PAY_PRIVATE_KEY_PATH=./certs/apiclient_key.pem
WECHAT_PAY_MERCHANT_SERIAL_NO=
WECHAT_PAY_PLATFORM_CERT_PATH=./certs/wechatpay_platform.pem
WECHAT_PAY_PUBLIC_KEY_PATH=./certs/wechatpay_public.pem
WECHAT_PAY_PUBLIC_KEY_ID=
```

说明：

- 当前项目已支持 **平台证书模式** 与 **微信支付公钥模式** 二选一用于回调验签
- 如果你已经在商户平台下载/查看到了微信支付公钥，推荐优先使用公钥模式

---

## 四、真实支付联调顺序

1. 后端切换到 `WECHAT_PAY_MODE=real`
2. 启动后端，确认 `/api/v1/payment/prepay` 不再返回 `mode=mock`
3. 小程序端创建待支付订单
4. 订单详情页调用 `prepay`
5. 小程序调起 `wx.requestPayment`
6. 微信支付回调 `/api/v1/payment/notify`
7. 后端验签、解密、更新订单状态为 `confirmed`
8. 前端轮询订单状态并刷新页面

---

## 四点五、本地支付链路检查脚本

在没有真实商户凭据前，可先用本地脚本检查订单支付状态推进是否正常：

```bash
python scripts/payment_sanity_check.py <order_no>
```

输出内容包括：

- 当前支付模式（mock / real）
- 当前订单状态
- 实付金额
- transaction_id
- paid_at

在 `mock` 模式下，可直接触发一次本地支付最终确认：

```bash
python scripts/payment_sanity_check.py <order_no> --mock-pay
```

也可以指定自定义 transaction_id：

```bash
python scripts/payment_sanity_check.py <order_no> --mock-pay --transaction-id mock_manual_001
```

这个脚本适合在接入真实微信支付前先验证：

- 订单状态是否能从 `unpaid` 推进到 `confirmed`
- transaction_id / paid_at 是否写入成功
- Redis 超时关闭逻辑是否会和支付确认打架

---

## 五、低风险上线建议

### 第一阶段：内测

- 只用低金额订单测试
- 只让内部账号支付
- 每笔支付都确认：
  - 前端支付成功
  - 后端收到 notify
  - 订单状态变为 `confirmed`
  - Redis 超时关闭逻辑未误伤已支付订单

### 第二阶段：小范围正式

- 开放少量真实用户
- 监控：
  - `prepay` 失败率
  - notify 失败率
  - 订单支付后未确认率

---

## 六、验收标准

以下全部满足才算真实微信支付接入完成：

- `/api/v1/payment/prepay` 返回 `mode=real`
- 小程序成功拉起微信支付收银台
- 支付成功后，后端 `notify` 成功返回 `SUCCESS`
- 订单从 `unpaid` 正确进入 `confirmed`
- 前端无需 mock 回调即可看到已支付状态
- 重复回调不会重复推进订单状态

---

## 七、当前剩余人工步骤

由于真实商户密钥不能由代码自动生成，当前仍需人工提供：

- AppID
- Secret
- mchid
- API v3 Key
- 商户私钥
- 商户证书序列号
- 平台证书
- HTTPS 回调域名

填完后即可切换到真实支付模式。
