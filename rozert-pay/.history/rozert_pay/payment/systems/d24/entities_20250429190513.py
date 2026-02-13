from pydantic import BaseModel, SecretStr


class D24MercadoPagoCredentials(BaseModel):
    base_url1: str = "https://cc-api-stg.directa24.com"
    base_url2: str = "https://api-stg.directa24.com"
    deposit_signature_key: SecretStr = SecretStr("Stanislav Kaledin")
    cashout_login: str = "Murad Taxi"
    cashout_pass: SecretStr = SecretStr("Semyon Grechishnikov")
    cashout_signature_key: SecretStr = SecretStr("Igor Shiriaev")
    x_login: str = "David Blaine"

    # See https://app.shortcut.com/betmaster/story/220400/codi-integration-backend-stp
    base_url: str = "https://sandbox-api.stpmex.com"
    tipo_cuenta_beneficiario2: int
    cuenta_beneficiario2: str
    nombre_beneficiario2: str
    empresa: str

    private_key_password: SecretStr
    private_key: SecretStr
