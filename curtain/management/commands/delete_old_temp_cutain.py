from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from curtain.models import Curtain, LastAccess
from django.db.models import Max

class Command(BaseCommand):
    help = 'Delete curtains with last access older than 90 days'

    def handle(self, *args, **options):
        # Get the date 90 days ago
        ninety_days_ago = timezone.now() - timedelta(days=90)

        # Get the latest LastAccess for each Curtain
        latest_last_accesses = LastAccess.objects.values('curtain').annotate(max_last_access=Max('last_access')).filter(max_last_access__lte=ninety_days_ago)

        # Get curtains with the latest last access older than 90 days
        curtains_to_delete = Curtain.objects.filter(id__in=[item['curtain'] for item in latest_last_accesses], permanent=False)

        # Delete these curtains
        curtains_to_delete.delete()

        self.stdout.write(self.style.SUCCESS('Successfully deleted old curtains'))