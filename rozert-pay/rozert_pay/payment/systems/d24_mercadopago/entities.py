from pydantic import BaseModel, SecretStr


class D24Credentials(BaseModel):
    base_url: str = "https://api-stg.directa24.com"
    base_url_for_credit_cards: str = "https://cc-api-stg.directa24.com"
    deposit_signature_key: SecretStr
    cashout_login: str
    cashout_pass: SecretStr
    cashout_signature_key: SecretStr
    x_login: str
