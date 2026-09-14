import json

import httpx
import pytest
from typer.testing import CliRunner

from edunet_cli import cli

from .conftest import LOGIN_URL, PAGE_INFO, SUCCESS_URL

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_credentials(monkeypatch):
    for key in (
        "EDUNET_USERNAME",
        "EDUNET_PASSWORD",
        "EDUNET_SERVER",
        "EDUNET_PROBE_URL",
        "EDUNET_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)


def bind(monkeypatch, make_client, handler):
    monkeypatch.setattr(cli, "PortalClient", lambda _: make_client(handler))


def test_help_and_version():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for word in ("login", "logout", "status", "doctor"):
        assert word in result.output
    assert "0.1.0" in runner.invoke(cli.app, ["--version"]).output


def test_status_json(monkeypatch, make_client):
    bind(monkeypatch, make_client, lambda _: httpx.Response(204))
    result = runner.invoke(cli.app, ["--json", "status"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["online"] is True


def test_missing_credentials_no_prompt(monkeypatch, make_client):
    bind(monkeypatch, make_client, lambda _: httpx.Response(200))
    result = runner.invoke(cli.app, ["--json", "login", "--no-input"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["event"] == "error"


def test_login_stdin_and_json_redaction(monkeypatch, make_client):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(204)
        if request.url.params["method"] == "pageInfo":
            return httpx.Response(200, json=PAGE_INFO)
        return httpx.Response(200, json={"result": "success", "userIndex": "do-not-print"})

    bind(monkeypatch, make_client, handler)
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "login",
            "--force",
            "-u",
            "secret-user",
            "--password-stdin",
            "--portal-url",
            LOGIN_URL,
        ],
        input="secret-password\n",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["authenticated"] is True
    for secret in ("secret-user", "secret-password", "do-not-print", "testmac"):
        assert secret not in result.output


def test_portal_success_probe_failure_exit_three(monkeypatch, make_client):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json=PAGE_INFO if request.url.params["method"] == "pageInfo" else {"result": "success"},
        )

    bind(monkeypatch, make_client, handler)
    result = runner.invoke(
        cli.app,
        ["--json", "login", "--portal-url", LOGIN_URL],
        env={"EDUNET_USERNAME": "test", "EDUNET_PASSWORD": "test"},
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["online"] is False


def test_already_online_no_credentials(monkeypatch, make_client):
    bind(monkeypatch, make_client, lambda _: httpx.Response(204))
    result = runner.invoke(cli.app, ["--json", "login"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["event"] == "already_online"


def test_logout_cli(monkeypatch, make_client):
    bind(monkeypatch, make_client, lambda _: httpx.Response(200, json={"result": "success"}))
    result = runner.invoke(cli.app, ["--json", "logout", "--success-url", SUCCESS_URL])
    assert result.exit_code == 0
    assert "synthetic-session" not in result.output


def test_doctor_cli(monkeypatch, make_client):
    bind(monkeypatch, make_client, lambda _: httpx.Response(200, json=PAGE_INFO))
    result = runner.invoke(cli.app, ["--json", "doctor", "--portal-url", LOGIN_URL])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["rsa_bits"] == 1024


def test_bad_timeout_json():
    result = runner.invoke(cli.app, ["--json", "--timeout", "0", "status"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize(
    "portal_status,probe_status,code", [(200, 204, 0), (500, 204, 1), (200, 200, 1), (500, 200, 1)]
)
def test_status_portal(monkeypatch, make_client, portal_status, probe_status, code):
    def handler(request):
        return httpx.Response(portal_status if request.url.host == "10.100.200.3" else probe_status)

    bind(monkeypatch, make_client, handler)
    result = runner.invoke(cli.app, ["--json", "status", "--portal"])
    assert result.exit_code == code
    data = json.loads(result.stdout)
    assert data["portal_reachable"] is (portal_status == 200)
    assert data["online"] is (probe_status == 204)
