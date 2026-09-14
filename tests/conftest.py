import httpx
import pytest

from edunet_cli.client import PortalClient, Settings

SERVER = "http://10.100.200.3"
LOGIN_URL = SERVER + "/eportal/index.jsp?wlanuserip=example&mac=testmac&ssid="
SUCCESS_URL = SERVER + "/eportal/success.jsp?userIndex=synthetic-session"
MODULUS = format(2**1024 - 109, "x")
PAGE_INFO = {"publicKeyExponent": "10001", "publicKeyModulus": MODULUS, "passwordEncrypt": "false"}


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must use MockTransport, not a real network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)


@pytest.fixture
def make_client():
    clients = []

    def factory(handler):
        client = PortalClient(Settings(), transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.http.close()
