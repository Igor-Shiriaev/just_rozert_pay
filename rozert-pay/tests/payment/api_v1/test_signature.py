# BEGIN doc.signature
import base64
import hashlib
import hmac


def sign_request(request_body: str, secret: str) -> str:
    secret_key = secret.encode()
    message = request_body
    signature = hmac.new(secret_key, message.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(signature)
    return signature.decode()


def test_signature():
    assert (
        sign_request("request_body", "secret")
        == "YSn6vnl9X09HPcTreSE93iT6pyZTcKIxlsnnEsKRuLk="
    )


# END doc.signature
