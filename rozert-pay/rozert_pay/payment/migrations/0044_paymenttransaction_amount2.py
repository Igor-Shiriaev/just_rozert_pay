import rozert_pay.common.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0043_add_cardpay_applepay_flag"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymenttransaction",
            name="amount2",
            field=rozert_pay.common.fields.MoneyField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="currency2",
            field=rozert_pay.common.fields.CurrencyField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="balance",
            field=rozert_pay.common.fields.MoneyField(default=0),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="hold_balance",
            field=rozert_pay.common.fields.MoneyField(default=0),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="operational_balance",
            field=rozert_pay.common.fields.MoneyField(
                default=0,
                help_text="Total funds, including confirmed and pending.",
            ),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="frozen_balance",
            field=rozert_pay.common.fields.MoneyField(
                default=0,
                help_text="Part of operational_balance that is temporarily locked.",
            ),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="pending_balance",
            field=rozert_pay.common.fields.MoneyField(
                default=0,
                help_text="Part of operational_balance that is awaiting settlement from a provider.",
            ),
        ),
        migrations.AlterField(
            model_name="currencywallet",
            name="currency",
            field=rozert_pay.common.fields.CurrencyField(),
        ),
        migrations.AlterField(
            model_name="paymenttransaction",
            name="currency",
            field=rozert_pay.common.fields.CurrencyField(),
        ),
    ]
