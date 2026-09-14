"""Interactive and machine-readable command-line interface."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import typer
from rich.console import Console

from . import __version__
from .client import DEFAULT_PROBE, DEFAULT_SERVER, PortalClient, Settings
from .errors import PortalError

app = typer.Typer(
    no_args_is_help=True,
    help="校园网 ePortal 登录工具。全局选项放在子命令前。",
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@dataclass
class Runtime:
    settings: Settings
    as_json: bool
    console: Console

    def emit(self, ok: bool, event: str, message: str, **data: Any) -> None:
        if self.as_json:
            typer.echo(
                json.dumps(
                    {"ok": ok, "event": event, "message": message, **data}, ensure_ascii=False
                )
            )
        else:
            self.console.print(message, style="green" if ok else "yellow", markup=False)

    def run(self, operation: Callable[[PortalClient], None]) -> None:
        try:
            with PortalClient(self.settings) as client:
                operation(client)
        except PortalError as exc:
            self.emit(False, "error", str(exc), exit_code=exc.code)
            raise typer.Exit(exc.code) from None
        except (KeyboardInterrupt, EOFError, typer.Abort):
            self.emit(False, "cancelled", "已取消。", exit_code=130)
            raise typer.Exit(130) from None


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"edunet {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    server: Annotated[
        str, typer.Option(envvar="EDUNET_SERVER", help="门户地址。")
    ] = DEFAULT_SERVER,
    probe_url: Annotated[
        str, typer.Option(envvar="EDUNET_PROBE_URL", help="期望返回空 204 的联网检测地址。")
    ] = DEFAULT_PROBE,
    timeout: Annotated[
        float, typer.Option(envvar="EDUNET_TIMEOUT", help="每个网络请求的超时秒数。")
    ] = 8.0,
    as_json: Annotated[
        bool, typer.Option("--json", help="输出单个 JSON 对象，禁用交互提示。")
    ] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="禁用彩色输出。")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=version_callback, is_eager=True, help="显示版本。")
    ] = False,
) -> None:
    try:
        settings = Settings(server=server, probe_url=probe_url, timeout=timeout)
    except PortalError as exc:
        if as_json:
            typer.echo(
                json.dumps(
                    {"ok": False, "event": "error", "message": str(exc), "exit_code": 2},
                    ensure_ascii=False,
                )
            )
        else:
            typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    ctx.obj = Runtime(settings, as_json, Console(no_color=no_color or "NO_COLOR" in os.environ))


@app.command()
def status(
    ctx: typer.Context,
    portal: Annotated[
        bool, typer.Option("--portal", help="同时检查校园网门户 HTTP 可达性。")
    ] = False,
) -> None:
    """检测外网连通性；--portal 同时检查校园网门户。"""
    rt: Runtime = ctx.obj

    def operation(client: PortalClient) -> None:
        online = client.online()
        data: dict[str, Any] = {"online": online}
        ok = online
        message = "外网探测通过。" if online else "外网探测未通过：可能未登录或探测站点不可达。"
        if portal:
            reachable = client.portal_reachable()
            data["portal_reachable"] = reachable
            ok = online and reachable
            message = f"校园网门户：{'可达' if reachable else '不可达'}；外网探测：{'通过' if online else '未通过'}。"
        rt.emit(ok, "status", message, **data)
        if not ok:
            raise typer.Exit(1)

    rt.run(operation)


@app.command()
def doctor(
    ctx: typer.Context,
    portal_url: Annotated[str | None, typer.Option(help="浏览器当前完整登录页地址。")] = None,
) -> None:
    """检查登录参数和 RSA 公钥，不提交账号密码。"""
    rt: Runtime = ctx.obj

    def operation(client: PortalClient) -> None:
        page = client.prepare_login(portal_url)
        rt.emit(
            True,
            "doctor",
            "登录参数和 RSA 公钥检查通过；未提交登录请求。",
            rsa_bits=int(page.modulus, 16).bit_length(),
        )

    rt.run(operation)


@app.command()
def login(
    ctx: typer.Context,
    username: Annotated[
        str | None,
        typer.Option("--username", "-u", envvar="EDUNET_USERNAME", help="账号；缺省时交互输入。"),
    ] = None,
    service: Annotated[
        str, typer.Option(envvar="EDUNET_SERVICE", help="服务名称；当前门户默认留空。")
    ] = "",
    portal_url: Annotated[
        str | None, typer.Option(help="自动发现失败时，传入当前完整登录页地址。")
    ] = None,
    password_stdin: Annotated[
        bool, typer.Option(help="从标准输入读取一行密码，优先于环境变量。")
    ] = False,
    no_input: Annotated[bool, typer.Option(help="禁止交互，缺少凭据直接退出。")] = False,
    force: Annotated[bool, typer.Option(help="外网已通时仍提交一次登录。")] = False,
    require_portal: Annotated[
        bool, typer.Option(help="登录前确认门户可达，适用于定时重连。")
    ] = False,
) -> None:
    """登录校园网；密码隐藏输入，也可设置 EDUNET_PASSWORD。"""
    rt: Runtime = ctx.obj

    def operation(client: PortalClient) -> None:
        if not force and client.online():
            rt.emit(True, "already_online", "外网探测通过，无需登录。", online=True)
            return
        if require_portal and not client.portal_reachable():
            raise PortalError("校园网门户不可达，跳过本次登录；请检查校园网连接。")
        name = username
        secret = os.getenv("EDUNET_PASSWORD")
        interactive = not (rt.as_json or no_input) and sys.stdin.isatty()
        if password_stdin:
            if sys.stdin.isatty():
                raise PortalError(
                    "--password-stdin 需要管道或重定向输入；终端请使用隐藏输入。", code=2
                )
            secret = sys.stdin.readline().rstrip("\r\n")
        if not name and interactive:
            name = typer.prompt("校园网账号")
        if not secret and interactive:
            secret = typer.prompt("校园网密码", hide_input=True)
        if not name or not name.strip() or not secret:
            raise PortalError(
                "缺少账号或密码。设置 EDUNET_USERNAME / EDUNET_PASSWORD，或使用 -u 与 --password-stdin。",
                code=2,
            )
        page = client.prepare_login(portal_url)
        client.login(page, name, secret, service)
        online = False
        for attempt in range(3):
            if attempt:
                time.sleep(2)
            if client.online():
                online = True
                break
        rt.emit(
            True,
            "login",
            "登录成功，外网探测通过。" if online else "门户确认登录成功，但外网探测未通过。",
            authenticated=True,
            online=online,
        )
        if not online:
            raise typer.Exit(3)

    rt.run(operation)


@app.command()
def logout(
    ctx: typer.Context,
    success_url: Annotated[
        str | None, typer.Option(help="自动发现失败时，传入当前完整登录成功页地址。")
    ] = None,
) -> None:
    """登出当前会话，无需重新输入密码。"""
    rt: Runtime = ctx.obj

    def operation(client: PortalClient) -> None:
        client.logout(success_url)
        rt.emit(True, "logout", "门户确认登出成功。")

    rt.run(operation)
