import xmltodict

def _generate_worldpay_xml(data: dict) -> str:
    """Generate WorldPay XML with proper DOCTYPE declaration."""
    xml_response = xmltodict.unparse(
        data, 
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
