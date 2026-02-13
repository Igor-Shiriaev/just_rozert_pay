#!/usr/bin/env python3
"""
Usage:
fab prod run:"cp ../bank_bins/bins.json.zip backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back"
fab prod run:"cp ../bank_bins/bins_updater.py backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back/betmaster/management/commands"
nohup python3 manage.py bins_updater &>/dev/null &
jobs
"""
import json
from argparse import ArgumentParser
from typing import Any

from django.core.management import BaseCommand
from rozert_pay.payment.models import Bank, PaymentCardBank


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--path")

    def handle(self, **options: Any) -> None:
        path = options.get("path", "bins.json")

        self.stdout.write(f"Try to open file: {path}")
        with open(path, 'rb') as file:
            self.stdout.write("File is opened")
            # Row example:
            # {"213100": {"br": 11, "bn": "Jcb Co., Ltd.", "cc": "JP"}}
            # {"<bin>": {"br": <card type>, "bn": "<bank name>", "cc": "country"}}
            self.stdout.write("Try to load json")
            card_bins = json.load(file)
            self.stdout.write("Json is loaded")
            self.stdout.write(f"Loaded {len(card_bins)} bins")

        bank_names = {cb["bn"] for cb in card_bins.values()}
        banks_by_name = {}
        for bank_name in bank_names:
            bank, _ = Bank.objects.get_or_create(name=bank_name)
            banks_by_name[bank_name] = bank.pk
            self.stdout.write(f"Created/found bank: {bank_name}")

        for card_bin, data in card_bins.items():
            _, created = PaymentCardBank.objects.update_or_create(
                bin=card_bin,
                defaults={
                    "bank_id": banks_by_name[data["bn"]],
                    "card_type": data["br"],
                    "card_class": data["type"],
                    "country": data["cc"],
                    "is_virtual": data["virtual"],
                    "is_prepaid": data["prepaid"],
                    "raw_category": data["raw_category"],
                },
            )
            self.stdout.write(f"Processed bin {card_bin}, created: {created}")
        #     card_banks_to_create.append(PaymentCardBank(
        #         bin=card_bin,
        #         bank_id=banks_by_name[data['bn']],
        #         card_type=data['br'],
        #         country=data['cc']
        #     ))
        # PaymentCardBank.objects.bulk_create(card_banks_to_create)
