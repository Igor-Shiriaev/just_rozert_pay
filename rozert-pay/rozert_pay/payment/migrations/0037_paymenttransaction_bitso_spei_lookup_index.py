from django.db import migrations, models
from django.db.models.functions import Upper
from rozert_pay.payment.models import BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0036_currencywallet_frozen_balance_and_more"),
    ]

    atomic = False

    state_operations = [
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(
                Upper(
                    models.Func(
                        models.F("extra"),
                        models.Value("claveRastreo"),
                        function="jsonb_extract_path_text",
                    )
                ),
                "amount",
                name=BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME,
                condition=models.Q(
                    system_type="bitso_spei",
                    type="withdrawal",
                    extra__has_key="claveRastreo",
                ),
            ),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[
                migrations.RunSQL(
                    f"""
CREATE INDEX "{BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME}" ON "payment_paymenttransaction" ((UPPER(jsonb_extract_path_text("extra", 'claveRastreo'))), "amount") WHERE ("extra" ? 'claveRastreo' AND "system_type" = 'bitso_spei' AND "type" = 'withdrawal');
                """
                )
            ],
        )
    ]
