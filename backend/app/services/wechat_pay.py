from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Mapping

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.models import Order


WECHAT_PAY_MODE_MOCK = "mock"
WECHAT_PAY_MODE_REAL = "real"
WECHAT_JSAPI_PATH = "/v3/pay/transactions/jsapi"
WECHAT_JSAPI_URL = f"https://api.mch.weixin.qq.com{WECHAT_JSAPI_PATH}"
NOTIFY_TIMESTAMP_TOLERANCE_SECONDS = 300


class WechatPayError(Exception):
    pass


class WechatPayConfigError(WechatPayError):
    pass


class WechatPayRequestError(WechatPayError):
    pass


class WechatPaySignatureError(WechatPayError):
    pass


@dataclass(slots=True)
class WechatPayNotification:
    order_no: str
    transaction_id: str
    paid_at: datetime | None
    appid: str
    mchid: str
    amount_total: int
    currency: str
    payer_openid: str | None


@dataclass(slots=True)
class WechatPayTradeState:
    order_no: str
    transaction_id: str | None
    trade_state: str
    trade_state_desc: str
    appid: str
    mchid: str
    amount_total: int
    currency: str
    payer_openid: str | None
    paid_at: datetime | None


def get_wechat_pay_mode() -> str:
    mode = (settings.WECHAT_PAY_MODE or WECHAT_PAY_MODE_MOCK).strip().lower()
    return mode if mode in {WECHAT_PAY_MODE_MOCK, WECHAT_PAY_MODE_REAL} else WECHAT_PAY_MODE_MOCK


def is_wechat_pay_real_mode() -> bool:
    return get_wechat_pay_mode() == WECHAT_PAY_MODE_REAL


def create_mock_prepay(order: Order) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce_str = secrets.token_hex(8)
    package = f"prepay_id=mock_{order.order_no}"
    digest = hashes.Hash(hashes.SHA256())
    digest.update(f"{order.order_no}:{order.actual_amount}:{nonce_str}".encode("utf-8"))
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "MD5",
        "paySign": digest.finalize().hex(),
        "mode": WECHAT_PAY_MODE_MOCK,
    }


async def create_prepay(order: Order, openid: str) -> dict[str, str]:
    if not is_wechat_pay_real_mode():
        return create_mock_prepay(order)
    return await _create_real_prepay(order, openid)


async def query_trade_state(order_no: str) -> WechatPayTradeState:
    if not is_wechat_pay_real_mode():
        raise WechatPayConfigError("当前不是微信真实模式，不能查询真实支付订单")

    _ensure_real_mode_config(require_platform_cert=False)
    if not order_no:
        raise WechatPayError("缺少订单号，无法查询支付状态")

    path = f"/v3/pay/transactions/out-trade-no/{order_no}?mchid={settings.WECHAT_MCHID}"
    timestamp = str(int(time.time()))
    nonce_str = secrets.token_hex(16)
    headers = {
        "Accept": "application/json",
        "Authorization": _build_authorization("GET", path, timestamp, nonce_str, ""),
        "Content-Type": "application/json",
        "User-Agent": "campus-food-backend/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.mch.weixin.qq.com{path}", headers=headers)
    except httpx.HTTPError as exc:
        raise WechatPayRequestError("请求微信支付订单查询失败") from exc

    if response.status_code >= 400:
        raise WechatPayRequestError(_extract_wechat_error_message(response).replace("统一下单", "订单查询"))

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise WechatPayRequestError("微信支付订单查询返回了无效响应") from exc

    return WechatPayTradeState(
        order_no=data.get("out_trade_no") or order_no,
        transaction_id=data.get("transaction_id"),
        trade_state=data.get("trade_state") or "",
        trade_state_desc=data.get("trade_state_desc") or "",
        appid=data.get("appid") or "",
        mchid=data.get("mchid") or "",
        amount_total=((data.get("amount") or {}).get("total") or 0),
        currency=((data.get("amount") or {}).get("currency") or ""),
        payer_openid=((data.get("payer") or {}).get("openid") or None),
        paid_at=_parse_paid_time(data.get("success_time")),
    )


def parse_wechat_pay_notification(
    headers: Mapping[str, str], body: bytes
) -> WechatPayNotification:
    _ensure_real_mode_config(require_platform_cert=False)
    body_text = body.decode("utf-8")
    timestamp = _header_value(headers, "Wechatpay-Timestamp")
    nonce = _header_value(headers, "Wechatpay-Nonce")
    signature = _header_value(headers, "Wechatpay-Signature")
    serial = _header_value(headers, "Wechatpay-Serial")
    if not timestamp or not nonce or not signature or not serial:
        raise WechatPaySignatureError("缺少微信支付回调签名头")
    expected_serial = _expected_wechatpay_serial()
    if expected_serial and serial != expected_serial:
        raise WechatPaySignatureError("微信支付回调平台序列号不匹配")
    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise WechatPaySignatureError("微信支付回调时间戳无效") from exc
    if abs(int(time.time()) - timestamp_int) > NOTIFY_TIMESTAMP_TOLERANCE_SECONDS:
        raise WechatPaySignatureError("微信支付回调时间戳已过期")

    public_key = _load_wechatpay_verify_public_key()
    message = f"{timestamp}\n{nonce}\n{body_text}\n".encode("utf-8")
    try:
        public_key.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise WechatPaySignatureError("微信支付回调验签失败") from exc

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise WechatPayError("微信支付回调数据格式错误") from exc

    transaction = json.loads(_decrypt_callback_resource(payload.get("resource") or {}))
    if transaction.get("trade_state") != "SUCCESS":
        raise WechatPayError("支付结果未成功")

    order_no = transaction.get("out_trade_no")
    transaction_id = transaction.get("transaction_id")
    if not order_no or not transaction_id:
        raise WechatPayError("微信支付回调缺少订单信息")

    return WechatPayNotification(
        order_no=order_no,
        transaction_id=transaction_id,
        paid_at=_parse_paid_time(transaction.get("success_time")),
        appid=transaction.get("appid") or "",
        mchid=transaction.get("mchid") or "",
        amount_total=((transaction.get("amount") or {}).get("total") or 0),
        currency=((transaction.get("amount") or {}).get("currency") or ""),
        payer_openid=((transaction.get("payer") or {}).get("openid") or None),
    )


async def _create_real_prepay(order: Order, openid: str) -> dict[str, str]:
    if not openid:
        raise WechatPayConfigError("当前用户缺少 openid，无法发起微信支付")
    _ensure_real_mode_config(require_platform_cert=False)

    body_dict = {
        "appid": settings.WECHAT_APPID,
        "mchid": settings.WECHAT_MCHID,
        "description": f"校内订餐订单{order.order_no}",
        "out_trade_no": order.order_no,
        "notify_url": settings.WECHAT_PAY_NOTIFY_URL,
        "amount": {"total": _amount_to_fen(order.actual_amount), "currency": "CNY"},
        "payer": {"openid": openid},
    }
    body = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time()))
    nonce_str = secrets.token_hex(16)
    headers = {
        "Accept": "application/json",
        "Authorization": _build_authorization(
            "POST", WECHAT_JSAPI_PATH, timestamp, nonce_str, body
        ),
        "Content-Type": "application/json",
        "User-Agent": "campus-food-backend/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WECHAT_JSAPI_URL, content=body.encode("utf-8"), headers=headers
            )
    except httpx.HTTPError as exc:
        raise WechatPayRequestError("请求微信支付统一下单失败") from exc

    if response.status_code >= 400:
        raise WechatPayRequestError(_extract_wechat_error_message(response))

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise WechatPayRequestError("微信支付统一下单返回了无效响应") from exc

    prepay_id = data.get("prepay_id")
    if not prepay_id:
        raise WechatPayRequestError("微信支付统一下单未返回 prepay_id")

    frontend_timestamp = str(int(time.time()))
    frontend_nonce = secrets.token_hex(16)
    frontend_package = f"prepay_id={prepay_id}"
    sign_message = (
        f"{settings.WECHAT_APPID}\n"
        f"{frontend_timestamp}\n"
        f"{frontend_nonce}\n"
        f"{frontend_package}\n"
    )
    return {
        "timeStamp": frontend_timestamp,
        "nonceStr": frontend_nonce,
        "package": frontend_package,
        "signType": "RSA",
        "paySign": _sign_message(sign_message),
        "mode": WECHAT_PAY_MODE_REAL,
    }


def _ensure_real_mode_config(require_platform_cert: bool) -> None:
    missing: list[str] = []
    required = {
        "WECHAT_APPID": settings.WECHAT_APPID,
        "WECHAT_MCHID": settings.WECHAT_MCHID,
        "WECHAT_API_V3_KEY": settings.WECHAT_API_V3_KEY,
        "WECHAT_PAY_NOTIFY_URL": settings.WECHAT_PAY_NOTIFY_URL,
        "WECHAT_PAY_MERCHANT_SERIAL_NO": settings.WECHAT_PAY_MERCHANT_SERIAL_NO,
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if not settings.WECHAT_PAY_PRIVATE_KEY and not settings.WECHAT_PAY_PRIVATE_KEY_PATH:
        missing.append("WECHAT_PAY_PRIVATE_KEY 或 WECHAT_PAY_PRIVATE_KEY_PATH")
    if require_platform_cert and not settings.WECHAT_PAY_PLATFORM_CERT_PATH:
        missing.append("WECHAT_PAY_PLATFORM_CERT_PATH")
    if not settings.WECHAT_PAY_PLATFORM_CERT_PATH and not settings.WECHAT_PAY_PUBLIC_KEY_PATH and not settings.WECHAT_PAY_PUBLIC_KEY:
        missing.append("WECHAT_PAY_PLATFORM_CERT_PATH 或 WECHAT_PAY_PUBLIC_KEY_PATH 或 WECHAT_PAY_PUBLIC_KEY")
    if len((settings.WECHAT_API_V3_KEY or "").encode("utf-8")) != 32:
        missing.append("WECHAT_API_V3_KEY(必须为32字节)")
    if missing:
        raise WechatPayConfigError("微信支付真实模式配置不完整: " + "、".join(missing))


def _load_private_key_text() -> str:
    if settings.WECHAT_PAY_PRIVATE_KEY:
        return settings.WECHAT_PAY_PRIVATE_KEY.replace("\\n", "\n")
    path = settings.WECHAT_PAY_PRIVATE_KEY_PATH.strip()
    if not path:
        raise WechatPayConfigError("未配置微信支付商户私钥")
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise WechatPayConfigError("读取微信支付商户私钥失败") from exc


def _load_private_key():
    try:
        return serialization.load_pem_private_key(
            _load_private_key_text().encode("utf-8"), password=None
        )
    except (TypeError, ValueError) as exc:
        raise WechatPayConfigError("微信支付商户私钥格式无效") from exc


def _load_platform_certificate() -> x509.Certificate:
    path = settings.WECHAT_PAY_PLATFORM_CERT_PATH.strip()
    if not path:
        raise WechatPayConfigError("未配置微信支付平台证书")
    try:
        content = Path(path).read_bytes()
    except OSError as exc:
        raise WechatPayConfigError("读取微信支付平台证书失败") from exc
    try:
        return x509.load_pem_x509_certificate(content)
    except ValueError as exc:
        raise WechatPayConfigError("微信支付平台证书格式无效") from exc


def _load_public_key_text() -> str:
    if settings.WECHAT_PAY_PUBLIC_KEY:
        return settings.WECHAT_PAY_PUBLIC_KEY.replace("\\n", "\n")
    path = settings.WECHAT_PAY_PUBLIC_KEY_PATH.strip()
    if not path:
        raise WechatPayConfigError("未配置微信支付公钥")
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise WechatPayConfigError("读取微信支付公钥失败") from exc


def _load_public_key() -> RSAPublicKey:
    try:
        public_key = serialization.load_pem_public_key(_load_public_key_text().encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise WechatPayConfigError("微信支付公钥格式无效") from exc
    if not isinstance(public_key, RSAPublicKey):
        raise WechatPayConfigError("微信支付公钥类型无效")
    return public_key


def _load_wechatpay_verify_public_key() -> RSAPublicKey:
    if settings.WECHAT_PAY_PUBLIC_KEY or settings.WECHAT_PAY_PUBLIC_KEY_PATH:
        return _load_public_key()

    cert = _load_platform_certificate()
    public_key = cert.public_key()
    if not isinstance(public_key, RSAPublicKey):
        raise WechatPayConfigError("微信支付平台证书公钥类型无效")
    return public_key


def _expected_wechatpay_serial() -> str:
    if settings.WECHAT_PAY_PUBLIC_KEY or settings.WECHAT_PAY_PUBLIC_KEY_PATH:
        return settings.WECHAT_PAY_PUBLIC_KEY_ID.strip()

    if settings.WECHAT_PAY_PLATFORM_CERT_PATH.strip():
        cert = _load_platform_certificate()
        return format(cert.serial_number, "X")

    return ""


def _build_authorization(
    method: str, canonical_url: str, timestamp: str, nonce_str: str, body: str
) -> str:
    message = f"{method}\n{canonical_url}\n{timestamp}\n{nonce_str}\n{body}\n"
    signature = _sign_message(message)
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{settings.WECHAT_MCHID}",'
        f'nonce_str="{nonce_str}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.WECHAT_PAY_MERCHANT_SERIAL_NO}",'
        f'signature="{signature}"'
    )


def _sign_message(message: str) -> str:
    private_key = _load_private_key()
    if not isinstance(private_key, RSAPrivateKey):
        raise WechatPayConfigError("微信支付商户私钥类型无效")

    signature = private_key.sign(
        message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")


def _decrypt_callback_resource(resource: dict) -> str:
    ciphertext = resource.get("ciphertext")
    nonce = resource.get("nonce")
    associated_data = resource.get("associated_data", "")
    if not ciphertext or not nonce:
        raise WechatPayError("微信支付回调缺少加密资源")
    try:
        plaintext = AESGCM(settings.WECHAT_API_V3_KEY.encode("utf-8")).decrypt(
            nonce.encode("utf-8"),
            base64.b64decode(ciphertext),
            associated_data.encode("utf-8") if associated_data else None,
        )
    except Exception as exc:
        raise WechatPayError("微信支付回调解密失败") from exc
    return plaintext.decode("utf-8")


def _parse_paid_time(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WechatPayError("微信支付成功时间格式无效") from exc


def _amount_to_fen(amount: Decimal | str) -> int:
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _header_value(headers: Mapping[str, str], key: str) -> str:
    return headers.get(key) or headers.get(key.lower()) or ""


def _extract_wechat_error_message(response: httpx.Response) -> str:
    prefix = "微信支付统一下单失败"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"{prefix}: HTTP {response.status_code}"
    detail = (
        payload.get("message")
        or payload.get("detail")
        or payload.get("code")
        or f"HTTP {response.status_code}"
    )
    return f"{prefix}: {detail}"
