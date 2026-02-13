import tempfile

import pytest
from django.conf import settings
from django.core.management import call_command


@pytest.mark.django_db
def test_swagger_doc_is_up_to_date():
    current_swagger_path = settings.BASE_DIR / "swagger.yml"
    assert current_swagger_path.exists(), "swagger.yml не найден"

    with current_swagger_path.open() as f:
        current_swagger = f.read()

    with tempfile.NamedTemporaryFile(suffix=".yml") as temp_swagger:
        call_command("spectacular", "--color", "--file", temp_swagger.name)

        with open(temp_swagger.name) as f:
            generated_swagger = f.read()

    if current_swagger != generated_swagger:
        raise AssertionError(
            "swagger.yml устарел. Пожалуйста, обновите его запустив: \n" "make swagger"
        )
