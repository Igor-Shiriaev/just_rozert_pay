from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0046_alter_paymenttransaction_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="operational_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                    ("suspended", "Suspended"),
                    ("terminated", "Terminated"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="merchant",
            name="risk_status",
            field=models.CharField(
                choices=[
                    ("white", "White"),
                    ("grey", "Grey"),
                    ("black", "Black"),
                ],
                default="white",
                max_length=20,
            ),
        ),
    ]
