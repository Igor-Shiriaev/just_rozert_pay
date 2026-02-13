#!/usr/bin/env python3
"""
Usage:
fab prod run:"cp ../bank_bins/bins.json.zip backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back"
fab prod run:"cp ../bank_bins/bins_updater.py \
    backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back/betmaster/management/commands"
nohup python3 manage.py bins_updater &>/dev/null &
jobs
"""
import json
from argparse import ArgumentParser
from typing import Any

from django.core.management import BaseCommand
from django.db import transaction
from rozert_pay.payment.models import Bank, PaymentCardBank


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--path", default="bins.json", help="Path to bins JSON file")
        parser.add_argument("--batch-size", type=int, default=1000,
                            help="Batch size for processing records")

    def handle(self, **options: Any) -> None:
        path: str = options["path"]
        batch_size: int = options["batch_size"]

        self.stdout.write(f"Loading bins data from: {path}")
        
        try:
            with open(path) as file:
                # Row example:
                # {"213100": {"br": 11, "bn": "Jcb Co., Ltd.", "cc": "JP"}}
                # {"<bin>": {"br": <card type>, "bn": "<bank name>", "cc": "country"}}
                card_bins = json.load(file)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Invalid JSON format: {e}"))
            return

        total_records = len(card_bins)
        self.stdout.write(f"Processing {total_records} records in batches of {batch_size}")

        # Process banks first
        self._process_banks(card_bins)
        
        # Process card banks in batches
        self._process_card_banks_in_batches(card_bins, batch_size)
        
        self.stdout.write(self.style.SUCCESS("Successfully processed all bins data"))

    def _process_banks(self, card_bins: dict[str, dict[str, Any]]) -> dict[str, int]:
        """Process and create banks, return mapping of bank names to IDs."""
        self.stdout.write("Processing banks...")
        
        bank_names = {cb["bn"] for cb in card_bins.values()}
        banks_by_name = {}
        
        with transaction.atomic():
            for bank_name in bank_names:
                try:
                    bank, created = Bank.objects.get_or_create(name=bank_name)
                    banks_by_name[bank_name] = bank.pk
                    if created:
                        self.stdout.write(f"Created bank: {bank_name}")
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"Error processing bank {bank_name}: {e}")
                    )
                    continue
        
        self.stdout.write(f"Processed {len(banks_by_name)} banks")
        return banks_by_name

    def _process_card_banks_in_batches(
        self, 
        card_bins: dict[str, dict[str, Any]], 
        batch_size: int
    ) -> None:
        """Process card banks in batches to avoid memory issues."""
        self.stdout.write("Processing card banks...")
        
        # Get bank name to ID mapping
        banks_by_name = dict(Bank.objects.values_list('name', 'pk'))
        
        items = list(card_bins.items())
        total_batches = (len(items) + batch_size - 1) // batch_size
        processed_count = 0
        error_count = 0
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(items))
            batch_items = items[start_idx:end_idx]
            
            self.stdout.write(f"Processing batch {batch_num + 1}/{total_batches} "
                            f"(records {start_idx + 1}-{end_idx})")
            
            with transaction.atomic():
                for card_bin, data in batch_items:
                    try:
                        bank_name = data.get("bn")
                        if not bank_name or bank_name not in banks_by_name:
                            self.stdout.write(
                                self.style.WARNING(f"Bank not found for bin {card_bin}: {bank_name}")
                            )
                            error_count += 1
                            continue
                        
                        _, created = PaymentCardBank.objects.update_or_create(
                            bin=card_bin,
                            defaults={
                                "bank_id": banks_by_name[bank_name],
                                "card_type": data.get("br"),
                                "card_class": data.get("type"),
                                "country": data.get("cc"),
                                "is_virtual": data.get("virtual", False),
                                "is_prepaid": data.get("prepaid", False),
                                "raw_category": data.get("raw_category"),
                            },
                        )
                        processed_count += 1
                        
                        if processed_count % 100 == 0:
                            self.stdout.write(f"Processed {processed_count} records...")
                            
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"Error processing bin {card_bin}: {e}")
                        )
                        error_count += 1
                        continue
        
        self.stdout.write(f"Completed: {processed_count} processed, {error_count} errors")
