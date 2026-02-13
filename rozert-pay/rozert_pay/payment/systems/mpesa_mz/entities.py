from pydantic import BaseModel, SecretStr


class MpesaMzCredentials(BaseModel):
    api_key: SecretStr
    public_key: str
    service_provider_code: str = "171717"
    base_url: str = "https://api.mpesa.vm.co.mz"
