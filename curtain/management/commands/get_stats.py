from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from request.models import Request

class Command(BaseCommand):
    """
    A command that get download stats from Request table and save it to a file
    """

    def add_arguments(self, parser):
        parser.add_argument('stats_type', type=str, help='Type of stats to be processed')
        parser.add_argument('data_type', type=str, help='Type of data to be processed', default="response")
        parser.add_argument('file_path', type=str, help='Path to the file to be saved')

    def handle(self, *args, **options):
        stats_type = options['stats_type']
        data_type = options['data_type']
        if stats_type in ("daily", "weekly", "monthly") and data_type in ("response", "id"):
            file_path = options['file_path']
            stats_data = Request.objects.filter(path__regex="\/curtain\/[a-z0-9\-]+\/download\/\w*")
            if stats_type == "daily":
                download_stats = (stats_data.annotate(date=TruncDay('time')).values('date').annotate(downloads=Count(data_type)))
            elif stats_type == "weekly":
                download_stats = (stats_data.annotate(date=TruncWeek('time')).values('date').annotate(downloads=Count(data_type)))
            elif stats_type == "monthly":
                download_stats = (stats_data.annotate(date=TruncMonth('time')).values('date').annotate(downloads=Count(data_type)))

            else:
                raise CommandError("Invalid stats type")
            with open(file_path, "w") as f:
                for stats in download_stats:
                    f.write(f"{stats['date'].strftime('%Y-%m-%d')}\t{stats['downloads']}\n")
        else:
            raise CommandError("Invalid stats type")