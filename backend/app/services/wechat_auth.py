from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.wechat_pay import is_wechat_pay_real_mode


class WechatAuthError(Exception):
    pass


class WechatAuthConfigError(WechatAuthError):
    pass


class WechatAuthRequestError(WechatAuthError):
    pass


async def exchange_code_for_openid(code: str) -> str:
    if not is_wechat_pay_real_mode():
        raise WechatAuthConfigError("当前不是微信真实模式，不能调用真实 openid 换取")

    if not settings.WECHAT_APPID or not settings.WECHAT_SECRET:
        raise WechatAuthConfigError("WECHAT_APPID 或 WECHAT_SECRET 未配置")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_APPID,
                    "secret": settings.WECHAT_SECRET,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError as exc:
        raise WechatAuthRequestError("请求微信 code2session 失败") from exc

    if response.status_code >= 400:
        raise WechatAuthRequestError(f"微信 code2session 返回 HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise WechatAuthRequestError("微信 code2session 返回无效 JSON") from exc

    if payload.get("errcode"):
        raise WechatAuthRequestError(
            f"微信 code2session 失败: {payload.get('errmsg') or payload.get('errcode')}"
        )

    openid = payload.get("openid")
    if not openid:
        raise WechatAuthRequestError("微信 code2session 未返回 openid")

    return openid
