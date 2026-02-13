#!/usr/bin/env python3
"""
Usage:
fab prod run:"cp ../bank_bins/bins.json.zip backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back"
fab prod run:"cp ../bank_bins/bins_updater.py backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back/betmaster/management/commands"
nohup python3 manage.py bins_updater &>/dev/null &
jobs
"""
import zipfile
from argparse import ArgumentParser
from typing import Any

import ujson

from payment.models import Bank, PaymentCardBank


class Command(BaseBackCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--path')

    def handle(self, **options: Any) -> None:
        fillin_bins(options.get('path', 'bins.json.zip'))


def fillin_bins(path='bins.json.zip'):
    with zipfile.ZipFile(path) as zfile:
        with zfile.open('bins.json') as file:
            # Row example:
            # {"213100": {"br": 11, "bn": "Jcb Co., Ltd.", "cc": "JP"}}
            # {"<bin>": {"br": <card type>, "bn": "<bank name>", "cc": "country"}}
            card_bins = ujson.load(file)

    # PaymentCardBank.objects.all().delete()
    # Bank.objects.all().delete()

    bank_names = {cb['bn'] for cb in card_bins.values()}
    banks_by_name = {}
    # exist_bank_names = Bank.objects.values_list('name', flat=True)
    for bank_name in bank_names:
        bank, _ = Bank.objects.get_or_create(name=bank_name)
        banks_by_name[bank_name] = bank.pk
        print(bank_name)
    # Bank.objects.bulk_create([Bank(name=bn) for bn in bank_names])
    # banks_by_name = dict(Bank.objects.values_list('name', 'pk'))

    # card_banks_to_create = []
    for card_bin, data in card_bins.items():
        _, created = PaymentCardBank.objects.update_or_create(
            bin=card_bin,
            defaults={
                'bank_id': banks_by_name[data['bn']],
                'card_type': data['br'],
                'card_class': data['type'],
                'country': data['cc'],
                'is_virtual': data['virtual'],
                'is_prepaid': data['prepaid'],
                'raw_category': data['raw_category'],
            },
        )
        print(card_bin, created)
    #     card_banks_to_create.append(PaymentCardBank(
    #         bin=card_bin,
    #         bank_id=banks_by_name[data['bn']],
    #         card_type=data['br'],
    #         country=data['cc']
    #     ))
    # PaymentCardBank.objects.bulk_create(card_banks_to_create)
