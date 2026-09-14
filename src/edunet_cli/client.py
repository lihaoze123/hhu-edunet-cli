"""HTTP transport and portal protocol. No disk persistence or POST retries."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import httpx

from .crypto import encrypt_password, validate_key
from .errors import PortalError

DEFAULT_SERVER = "http://10.100.200.3"
DEFAULT_PROBE = "http://connectivitycheck.gstatic.com/generate_204"


def origin(url: str) -> tuple[str, str, int]:
    try:
        p = urlsplit(url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            raise ValueError
        return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        raise PortalError("地址必须是有效的 HTTP(S) URL，且不能包含账号或密码。") from None


@dataclass(frozen=True)
class Settings:
    server: str = DEFAULT_SERVER
    probe_url: str = DEFAULT_PROBE
    timeout: float = 8.0

    def __post_init__(self) -> None:
        origin(self.server)
        origin(self.probe_url)
        p = urlsplit(self.server)
        if p.path not in {"", "/"} or p.query or p.fragment:
            raise PortalError("--server 只能包含协议、主机和可选端口。", code=2)
        if not 0 < self.timeout <= 120:
            raise PortalError("超时必须大于 0 且不超过 120 秒。", code=2)
        object.__setattr__(self, "server", self.server.rstrip("/"))


@dataclass(frozen=True)
class LoginPage:
    url: str
    query: str
    mac: str
    exponent: str
    modulus: str


class PortalClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.http = httpx.Client(
            timeout=settings.timeout,
            trust_env=False,
            follow_redirects=False,
            headers={"User-Agent": "edunet-cli/0.1.0"},
            transport=transport,
        )

    def __enter__(self) -> PortalClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def get(self, url: str) -> httpx.Response:
        # Follow GET redirects explicitly; never forward a credential-bearing POST.
        try:
            for _ in range(6):
                origin(url)
                response = self.http.get(url)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise PortalError("门户重定向缺少目标地址。")
                    url = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                return response
        except httpx.HTTPError:
            raise PortalError("网络请求失败，请确认校园网连接和门户地址。") from None
        raise PortalError("门户重定向次数过多。")

    def portal_reachable(self) -> bool:
        """An HTTP response from the configured portal, not proof of authentication."""
        try:
            response = self.http.get(self.settings.server + "/")
            return 200 <= response.status_code < 400
        except httpx.HTTPError:
            return False

    def online(self) -> bool:
        try:
            # A redirect is not evidence of connectivity, even if it later returns 204.
            response = self.http.get(self.settings.probe_url)
            return response.status_code == 204 and not response.content
        except httpx.HTTPError:
            return False

    def post(
        self, method: str, fields: dict[str, str], referer: str, *, double: bool = False
    ) -> dict[str, Any]:
        if origin(referer) != origin(self.settings.server):
            raise PortalError("认证页面与配置的门户地址不一致。")
        if double:
            fields = {k: quote(v, safe="~()*!.'-") for k, v in fields.items()}
        try:
            response = self.http.post(
                self.settings.server + "/eportal/InterFace.do",
                params={"method": method},
                data=fields,
                headers={"Referer": referer},
            )
            if response.is_redirect:
                raise PortalError("认证接口发生重定向，已停止提交。")
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPError:
            raise PortalError("认证请求失败，结果可能未确认；请检查网页状态后再操作。") from None
        except ValueError:
            raise PortalError("门户未返回有效 JSON，请检查当前网页登录页面。") from None
        if not isinstance(result, dict):
            raise PortalError("门户响应格式不符合预期。")
        return result

    def page_value(self, url: str, *, success: bool) -> str | None:
        try:
            if origin(url) != origin(self.settings.server):
                return None
            p = urlsplit(url)
            expected = "/eportal/success.jsp" if success else "/eportal/index.jsp"
            if p.path != expected or p.fragment:
                return None
            fields = parse_qs(p.query)
            if success:
                indexes = fields.get("userIndex", [])
                return indexes[0] if len(indexes) == 1 else None
            if all(len(fields.get(key, [])) == 1 for key in ("wlanuserip", "mac")):
                return p.query
        except (ValueError, PortalError):
            pass
        return None

    def discover(self, supplied: str | None = None, *, success: bool = False) -> tuple[str, str]:
        option = "--success-url" if success else "--portal-url"
        if supplied:
            value = self.page_value(supplied, success=success)
            if value:
                return supplied, value
            raise PortalError(
                f"{option} 必须是当前门户的完整{'成功' if success else '登录'}页地址，包含会话或网络参数。",
                code=2,
            )
        seeds = [
            self.settings.server + "/eportal/redirectortosuccess.jsp",
            self.settings.server + "/",
        ]
        if not success:
            seeds.append(self.settings.probe_url)
        for seed in seeds:
            try:
                response = self.get(seed)
            except PortalError:
                continue
            text = html.unescape(response.text).replace(r"\/", "/")
            candidates = [str(response.url)] + re.findall(
                r"""https?://[^\s<>"']+|(?:/eportal/)?(?:index|success)\.jsp\?[^\s<>"']+""", text
            )
            for candidate in candidates:
                url = urljoin(str(response.url), candidate)
                value = self.page_value(url, success=success)
                if value:
                    return url, value
        raise PortalError(
            f"未获取到当前{'会话' if success else '登录参数'}。请从浏览器复制完整页面地址，通过 {option} 传入。"
        )

    def prepare_login(self, supplied: str | None = None) -> LoginPage:
        url, query = self.discover(supplied)
        info = self.post("pageInfo", {"queryString": query}, url)
        if info.get("validCodeUrl") or info.get("isCheckSmsAuth") in (True, "true"):
            raise PortalError("门户要求验证码或短信验证，请使用网页登录。")
        exponent, modulus = info.get("publicKeyExponent"), info.get("publicKeyModulus")
        if not isinstance(exponent, str) or not isinstance(modulus, str):
            raise PortalError("门户未返回 RSA 公钥。")
        validate_key(exponent, modulus)
        return LoginPage(url, query, parse_qs(query)["mac"][0], exponent, modulus)

    def login(self, page: LoginPage, username: str, password: str, service: str = "") -> None:
        if not username.strip() or not password:
            raise PortalError("账号和密码不能为空。", code=2)
        encrypted = encrypt_password(password, page.mac, page.exponent, page.modulus)
        result = self.post(
            "login",
            {
                "userId": username.strip(),
                "password": encrypted,
                "service": service,
                "queryString": page.query,
                "operatorPwd": "",
                "operatorUserId": "",
                "validcode": "",
                "passwordEncrypt": "true",
            },
            page.url,
            double=True,
        )
        if result.get("result") != "success":
            raise PortalError("门户未确认登录成功。请在网页登录页检查密码、验证码或账号状态。")

    def logout(self, supplied: str | None = None) -> None:
        url, index = self.discover(supplied, success=True)
        result = self.post("logout", {"userIndex": index}, url)
        if result.get("result") != "success":
            raise PortalError("门户未确认登出成功，请在成功页检查当前会话状态。")
