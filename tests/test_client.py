from urllib.parse import parse_qs, unquote

import httpx
import pytest

from edunet_cli.client import Settings
from edunet_cli.errors import PortalError

from .conftest import LOGIN_URL, PAGE_INFO, SERVER, SUCCESS_URL


def test_login_encoding_and_single_post(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.params["method"] == "pageInfo":
            assert parse_qs(request.content.decode())["queryString"] == [LOGIN_URL.split("?", 1)[1]]
            return httpx.Response(200, json=PAGE_INFO)
        data = {
            k: unquote(v[0])
            for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()
        }
        assert data["userId"] == "user+&测试"
        assert data["service"] == ""
        assert data["passwordEncrypt"] == "true"
        assert data["queryString"] == LOGIN_URL.split("?", 1)[1]
        assert "test-password" not in request.content.decode()
        assert len(data["password"]) == 256
        return httpx.Response(200, json={"result": "success"})

    client = make_client(handler)
    client.login(client.prepare_login(LOGIN_URL), "user+&测试", "test-password")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://example.org/leak"}),
        httpx.Response(500),
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"result": "fail"}),
    ],
)
def test_logout_failure_does_not_retry_or_follow(make_client, response):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(PortalError):
        make_client(handler).logout(SUCCESS_URL)
    assert len(calls) == 1


def test_logout_form(make_client):
    def handler(request):
        assert request.method == "POST"
        assert request.url.params["method"] == "logout"
        assert parse_qs(request.content.decode()) == {"userIndex": ["synthetic-session"]}
        return httpx.Response(200, json={"result": "success"})

    make_client(handler).logout(SUCCESS_URL)


@pytest.mark.parametrize(
    "bad",
    [
        LOGIN_URL.replace("10.100.200.3", "example.org"),
        LOGIN_URL.replace("http:", "https:"),
        LOGIN_URL.replace("10.100.200.3", "10.100.200.3:8080"),
        LOGIN_URL + "&mac=duplicate",
        LOGIN_URL.replace("index.jsp", "success.jsp"),
        LOGIN_URL.replace("http://", "http://user:pass@"),
    ],
)
def test_reject_foreign_or_ambiguous_page(make_client, bad):
    client = make_client(lambda _: pytest.fail("must not make request"))
    with pytest.raises(PortalError):
        client.discover(bad)


@pytest.mark.parametrize(
    "body",
    [
        '<script>location.href="/eportal/index.jsp?wlanuserip=example&mac=testmac&ssid="</script>',
        '<meta http-equiv="refresh" content="0;url=http://10.100.200.3/eportal/index.jsp?wlanuserip=example&amp;mac=testmac&amp;ssid=">',
    ],
)
def test_html_discovery(make_client, body):
    client = make_client(lambda _: httpx.Response(200, text=body))
    assert client.discover()[0] == LOGIN_URL


def test_relative_success_discovery(make_client):
    client = make_client(
        lambda _: httpx.Response(
            200, text='<script>location="success.jsp?userIndex=synthetic-session"</script>'
        )
    )
    assert client.discover(success=True) == (SUCCESS_URL, "synthetic-session")


def test_http_redirect_discovery(make_client):
    def handler(request):
        if request.url.path == "/eportal/index.jsp":
            return httpx.Response(200)
        return httpx.Response(302, headers={"location": LOGIN_URL})

    assert make_client(handler).discover()[0] == LOGIN_URL


def test_redirect_loop_bounded(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": SERVER})

    with pytest.raises(PortalError, match="次数"):
        make_client(handler).get(SERVER)
    assert len(calls) == 6


def test_timeout_redacted(make_client):
    def handler(request):
        raise httpx.ReadTimeout("secret URL and password", request=request)

    client = make_client(handler)
    assert not client.online()
    with pytest.raises(PortalError) as exc:
        client.logout(SUCCESS_URL)
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize(
    "status,body,expected",
    [(204, b"", True), (200, b"", False), (204, b"unexpected", False), (302, b"", False)],
)
def test_probe(make_client, status, body, expected):
    assert make_client(lambda _: httpx.Response(status, content=body)).online() is expected


@pytest.mark.parametrize(
    "changes",
    [{"validCodeUrl": "/captcha"}, {"isCheckSmsAuth": "true"}, {"publicKeyModulus": None}],
)
def test_unsupported_portal(make_client, changes):
    client = make_client(lambda _: httpx.Response(200, json=PAGE_INFO | changes))
    with pytest.raises(PortalError):
        client.prepare_login(LOGIN_URL)


@pytest.mark.parametrize(
    "server",
    [
        "ftp://example.org",
        "http://example.org/path",
        "http://user:secret@example.org",
        "http://example.org:bad",
    ],
)
def test_settings_reject_invalid_server(server):
    with pytest.raises(PortalError):
        Settings(server=server)


@pytest.mark.parametrize("status,expected", [(200, True), (302, True), (403, False), (500, False)])
def test_portal_reachability(make_client, status, expected):
    assert make_client(lambda _: httpx.Response(status)).portal_reachable() is expected


def test_portal_timeout(make_client):
    def handler(request):
        raise httpx.ConnectTimeout("private", request=request)

    assert not make_client(handler).portal_reachable()
