import xmltodict


def generate_worldpay_xml(payload: dict) -> str:
    """Generate WorldPay XML with proper DOCTYPE declaration."""
    xml_response = xmltodict.unparse(
        payload, 
        pretty=True,
        full_document=True,
        encoding="UTF-8"
    )
    doctype = (
        "<!DOCTYPE paymentService PUBLIC "
        '"-//Worldpay//DTD Worldpay PaymentService v1//EN" '
        '"http://dtd.worldpay.com/paymentService_v1.dtd">'
    )
    parts = xml_response.split("\n", 1)
    return f"{parts[0]}\n{doctype}\n{parts[1]}"
