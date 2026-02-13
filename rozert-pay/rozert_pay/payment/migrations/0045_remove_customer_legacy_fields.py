# SAFE MIGRATION

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0044_paymenttransaction_amount2"),
    ]

    state_operations = [
        migrations.RemoveField(
            model_name="customer",
            name="_email",
        ),
        migrations.RemoveField(
            model_name="customer",
            name="_phone",
        ),
        migrations.RemoveField(
            model_name="customer",
            name="_extra",
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[
                migrations.RunSQL(
                    """
ALTER TABLE "payment_customer" ALTER COLUMN "email" DROP NOT NULL;
ALTER TABLE "payment_customer" ALTER COLUMN "phone" DROP NOT NULL;
ALTER TABLE "payment_customer" ALTER COLUMN "extra" DROP NOT NULL;
                """
                )
            ],
        )
    ]
