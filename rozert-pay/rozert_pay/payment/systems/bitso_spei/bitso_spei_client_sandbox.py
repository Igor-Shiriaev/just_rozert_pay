from rozert_pay.payment.services import base_classes
from rozert_pay.payment.systems.bitso_spei.client import BitsoSpeiClient, BitsoSpeiCreds


class BitsoSpeiClientSandbox(
    base_classes.BaseSandboxClientMixin[BitsoSpeiCreds], BitsoSpeiClient
):
    pass
