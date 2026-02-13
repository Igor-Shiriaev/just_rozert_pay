from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)
from django.core.management import call_command


class Command(StaticfilesRunserverCommand):
    def get_handler(self, *args, **options):  # type: ignore
        call_command("spectacular", "--color", "--file", "swagger.yml")
        return super().get_handler(*args, **options)
