#!/usr/bin/env python3
"""
Usage:
fab prod run:"cp ../bank_bins/bins.json.zip backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back"
fab prod run:"cp ../bank_bins/bins_updater.py backend-cronjob-7b6c7d4c78-c8vvc:/www/back/back/betmaster/management/commands"
nohup python3 manage.py bins_updater &>/dev/null &
jobs
"""
import gc
import json
import psutil
from argparse import ArgumentParser
from typing import Any

from django.core.management import BaseCommand
from django.db import transaction
from rozert_pay.payment.models import Bank, PaymentCardBank


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--path")
        parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for processing")

    def _log_memory_usage(self, stage: str) -> None:
        """Log current memory usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.stdout.write(f"[{stage}] Memory usage: {memory_mb:.1f} MB")

    def handle(self, **options: Any) -> None:
        path = options.get("path", "bins.json")
        batch_size = options.get("batch_size", 1000)

        self._log_memory_usage("Start")
        
        self.stdout.write(f"Try to open file: {path}")
        with open(path) as file:
            self.stdout.write("File is opened")
            # Row example:
            # {"213100": {"br": 11, "bn": "Jcb Co., Ltd.", "cc": "JP"}}
            # {"<bin>": {"br": <card type>, "bn": "<bank name>", "cc": "country"}}
            self.stdout.write("Try to load json")
            card_bins = json.load(file)
            self.stdout.write("Json is loaded")
            self.stdout.write(f"Loaded {len(card_bins)} bins")
        
        self._log_memory_usage("After JSON load")
        
        # Process banks in batches to save memory
        bank_names = {cb["bn"] for cb in card_bins.values()}
        total_banks = len(bank_names)
        self.stdout.write(f"Processing {total_banks} unique banks")
        
        banks_by_name = {}
        bank_list = list(bank_names)
        
        # Process banks in batches
        for i in range(0, len(bank_list), batch_size):
            batch_banks = bank_list[i:i + batch_size]
            self.stdout.write(f"Processing banks batch {i//batch_size + 1}/{(len(bank_list) + batch_size - 1)//batch_size}")
            
            for bank_name in batch_banks:
                bank, _ = Bank.objects.get_or_create(name=bank_name)
                banks_by_name[bank_name] = bank.pk
                self.stdout.write(f"Created/found bank: {bank_name}")
            
            # Force garbage collection after each batch
            gc.collect()
            
        self._log_memory_usage("After banks processing")
        
        # Process card bins in batches
        card_bins_items = list(card_bins.items())
        total_bins = len(card_bins_items)
        self.stdout.write(f"Processing {total_bins} card bins in batches of {batch_size}")
        
        for i in range(0, len(card_bins_items), batch_size):
            batch_items = card_bins_items[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(card_bins_items) + batch_size - 1) // batch_size
            
            self.stdout.write(f"Processing batch {batch_num}/{total_batches} ({len(batch_items)} items)")
            
            # Use transaction for batch processing
            with transaction.atomic():
                for card_bin, data in batch_items:
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
                    if created:
                        self.stdout.write(f"Created bin {card_bin}")
            
            # Log progress and force garbage collection after each batch
            progress = (i + len(batch_items)) / total_bins * 100
            self.stdout.write(f"Progress: {progress:.1f}% ({i + len(batch_items)}/{total_bins})")
            
            # Force garbage collection and log memory usage every 10 batches
            gc.collect()
            if batch_num % 10 == 0:
                self._log_memory_usage(f"After batch {batch_num}")
        
        # Clear large variables to free memory
        del card_bins
        del card_bins_items
        del banks_by_name
        gc.collect()
        
        self._log_memory_usage("Completed")
        self.stdout.write("BINs update completed successfully")
