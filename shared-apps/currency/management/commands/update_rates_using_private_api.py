import logging

from bm.betmaster_api import BetmasterServerAPI
from bm.utils import log_errors
from currency.models import Rate
from django.core.management.base import BaseCommand

logger = logging.getLogger('currency')

class Command(BaseCommand):
    @log_errors
    def handle(self, **options) -> None:    # type: ignore
        resp = BetmasterServerAPI().get_currency_exchange_rates()
        Rate.objects.create(
            datetime_calculated=resp.datetime_calculated,
            data={cur: format(value, 'f') for cur, value in resp.exchange_rates.items()},
        )
        logger.info('rates updated %s', resp.exchange_rates)
