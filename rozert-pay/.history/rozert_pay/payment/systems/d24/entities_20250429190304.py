from django.db.models import TextChoices
from pydantic import BaseModel, SecretStr


class StpCodiCredentials(BaseModel):
    # See https://app.shortcut.com/betmaster/story/220400/codi-integration-backend-stp
    base_url: str = "https://sandbox-api.stpmex.com"
    tipo_cuenta_beneficiario2: int
    cuenta_beneficiario2: str
    nombre_beneficiario2: str
    empresa: str

    private_key_password: SecretStr
    private_key: SecretStr


class StpCodiDepositType(TextChoices):
    APP = "app"
    QR_CODE = "qr_code"
