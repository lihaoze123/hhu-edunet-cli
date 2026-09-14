import json
from pathlib import Path

import pytest

from edunet_cli.crypto import encrypt_password, validate_key
from edunet_cli.errors import PortalError

from .conftest import MODULUS

# Fixed outputs from portal RSAUtils with a synthetic modulus and synthetic inputs.
VECTORS = json.loads(Path(__file__).with_name("rsa_vectors.json").read_text())


@pytest.mark.parametrize("vector", VECTORS)
def test_portal_js_vectors(vector):
    assert encrypt_password(vector["password"], "testmac", "10001", MODULUS) == vector["encrypted"]


def test_unicode_explicitly_rejected():
    with pytest.raises(PortalError, match="ASCII"):
        encrypt_password("中文🔑", "testmac", "10001", MODULUS)


@pytest.mark.parametrize(
    "exponent,modulus", [("oops", MODULUS), ("2", MODULUS), ("10001", "ff"), ("10001", "f" * 4096)]
)
def test_invalid_key(exponent, modulus):
    with pytest.raises(PortalError):
        validate_key(exponent, modulus)
