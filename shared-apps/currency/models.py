import decimal
from decimal import Decimal
from typing import Optional

from bm.utils import DECIMAL_PRECISION_CTX, quantize_decimal
from currency.const import CURRENCIES_EXCLUDED_FROM_DECIMAL_PLACES_CHECK, FOREIGN_CURRENCIES
from django.db import models
from django.db.models.fields import AutoField

from .const import USD
from .helpers import CURRENCY_MULTIPLIERS, get_currency_decimal_places


class UnknownCurrency(Exception):
    pass


class Rate(models.Model):
    # Context for intermediate multiplication without loss of precision
    _MULT_CTX = decimal.Context(
        prec=decimal.MAX_PREC,
        traps=[
            decimal.DivisionByZero,
            decimal.FloatOperation,
            decimal.Inexact,
            decimal.InvalidOperation,
            decimal.Overflow,
        ]
    )
    # 0 is min number of places, 18 is max number of decimal places (
    # ETH and similar crypto).
    _PLACES_MAP = {i: Decimal(10) ** -i for i in range(1, 19)}
    id = AutoField(primary_key=True)
    datetime = models.DateTimeField(auto_now_add=True)
    datetime_calculated = models.DateTimeField()
    data = models.JSONField()

    @classmethod
    def scale_crypto(
        cls,
        amount: Decimal,
        currency_from: str,
        currency_to: str,
        places: Optional[int]
    ) -> Decimal:

        scale_groups = [key for key in CURRENCY_MULTIPLIERS.keys()
                        if currency_from in key]
        assert len(scale_groups) == 1, \
            f'No scale groups or more than one group for {currency_from}'

        scale_group = scale_groups[0]
        assert currency_from in scale_group and currency_to in scale_group, \
            f'Can\'t scale {currency_from} to {currency_to}'

        multipliers = CURRENCY_MULTIPLIERS[scale_group]
        result_multiplier = DECIMAL_PRECISION_CTX.divide(
            multipliers[currency_from], multipliers[currency_to])

        result = cls._MULT_CTX.multiply(amount, result_multiplier)

        return quantize_decimal(result, places)

    def convert(
        self,
        amount: Decimal,
        currency_from: str,
        currency_to: str,
        places: Optional[int] = -1
    ) -> Decimal:
        """If places == -1, get_currency_decimal_places defines the 'places' value."""

        if places == -1:
            places = get_currency_decimal_places(currency_to)
        if (
            currency_to in FOREIGN_CURRENCIES
            and currency_to not in CURRENCIES_EXCLUDED_FROM_DECIMAL_PLACES_CHECK
        ):
            assert places > 2, f'Crypto currencies must be processed with more than 2 decimal places'   # type: ignore

        if currency_from != currency_to:
            if currency_to != USD:
                amount = self._MULT_CTX.multiply(
                    amount,
                    self.decimal_rate(currency_to)
                )
            if currency_from != USD:
                amount = DECIMAL_PRECISION_CTX.divide(
                    amount,
                    self.decimal_rate(currency_from)
                )

        return quantize_decimal(amount, places)

    def decimal_rate(self, currency: str) -> Decimal:
        try:
            return Decimal(self.data[currency])
        except KeyError:
            raise UnknownCurrency(currency)
