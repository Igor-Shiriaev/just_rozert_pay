#!/usr/bin/env python3
"""
Usage:
fab prod run:"cp ../bank_bins/bins.json.zip backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back"
fab prod run:"cp ../bank_bins/bins_updater.py backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back/betmaster/management/commands"
nohup python3 manage.py bins_updater &>/dev/null &
jobs
"""
import ijson
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
            self.stdout.write("Try to stream parse json")
            
            # Stream parse JSON to avoid loading entire file into memory
            bank_names = set()
            
            # First pass: collect bank names
            parser = ijson.parse(file)
            for prefix, event, value in parser:
                if event == 'string' and prefix.endswith('.bn'):
                    bank_names.add(value)
            
            # Reset file pointer for second pass
            file.seek(0)
            
            self.stdout.write(f"Found {len(bank_names)} unique banks")
        
        # Process banks first
        banks_by_name = {}
        for bank_name in bank_names:
            bank, _ = Bank.objects.get_or_create(name=bank_name)
            banks_by_name[bank_name] = bank.pk
            self.stdout.write(f"Created/found bank: {bank_name}")

        # Second pass: process card bins one by one
        with open(path, 'rb') as file:
            self.stdout.write("Processing card bins")
            
            # Parse each bin entry as it comes
            objects = ijson.items(file, '', multiple_values=False)
            card_bins = next(objects)  # Get the main object
            
            processed_count = 0
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
                processed_count += 1
                if processed_count % 1000 == 0:
                    self.stdout.write(f"Processed {processed_count} bins")
                    
            self.stdout.write(f"Completed processing {processed_count} bins")
