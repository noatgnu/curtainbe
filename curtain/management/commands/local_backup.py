import logging
import os
import subprocess
import socket
from django.core.management.base import BaseCommand
from django.utils import timezone



class Command(BaseCommand):
    help = 'Run database and media backups with logging to BackupLog model'

    def handle(self, *args, **options):
        current_time = timezone.now()
        logging.log(
            logging.INFO,
            f"Starting backup at {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        subprocess.run(
            ["python", "manage.py", "dbbackup", "--compress", "--output", f"/backups/db_backup_{current_time.strftime('%Y%m%d_%H%M%S')}.sql.gz"],
            check=True
        )
        logging.log(
            logging.INFO,
            f"Database backup completed at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

