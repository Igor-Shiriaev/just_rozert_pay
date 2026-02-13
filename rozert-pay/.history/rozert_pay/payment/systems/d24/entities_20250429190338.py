from pydantic import BaseModel, SecretStr


class D24MercadoPagoCredentials(BaseModel):
    # See https://app.shortcut.com/betmaster/story/220400/codi-integration-backend-stp
    base_url: str = "https://sandbox-api.stpmex.com"
    tipo_cuenta_beneficiario2: int
    cuenta_beneficiario2: str
    nombre_beneficiario2: str
    empresa: str

    private_key_password: SecretStr
    private_key: SecretStr
