"""Manually recover audits stuck in a running state after a worker crash."""

from django.core.management.base import BaseCommand

from audits.state_machine import recover_stale_tasks


class Command(BaseCommand):
    help = "Mark stale running audits/investigations as interrupted (evidence is retained)."

    def handle(self, *args, **options):
        result = recover_stale_tasks()
        self.stdout.write(
            self.style.SUCCESS(
                f"Recovered {result['audits']} audit(s) and {result['investigations']} "
                "investigation(s)."
            )
        )
