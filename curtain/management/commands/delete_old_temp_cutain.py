from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from curtain.models import Curtain, LastAccess
from django.db.models import Max


class Command(BaseCommand):
    help = 'Delete curtains with last access older than 90 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without deleting any curtains',
        )

    def handle(self, *args, **options):
        # Get the date 90 days ago
        ninety_days_ago = timezone.now() - timedelta(days=90)

        # Get the latest LastAccess for each Curtain
        latest_last_accesses = LastAccess.objects.values('curtain').annotate(max_last_access=Max('last_access')).filter(
            max_last_access__lte=ninety_days_ago)

        # Get the curtains to delete that is older than 90 days
        curtains_to_delete = Curtain.objects.filter(last_access__in=latest_last_accesses)

        if options['dry_run']:
            self.stdout.write('Dry run mode enabled. The following curtains would be deleted:')
            for curtain in curtains_to_delete:
                self.stdout.write(f'Curtain ID: {curtain.id}, Last Access: {curtain.last_access}')
        else:
            # Delete these curtains
            curtains_to_delete.delete()
            self.stdout.write(self.style.SUCCESS('Successfully deleted old curtains'))