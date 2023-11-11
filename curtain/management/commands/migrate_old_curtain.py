import json
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from curtain.models import Curtain
from django.contrib.auth.models import User

class Command(BaseCommand):
    """
    A command that load json fixture file and convert it to new curtain table.
    """
    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the old curtain file')

    def handle(self, *args, **options):

        file_path = options['file_path']
        with open(file_path, "r") as f:
            data = json.load(f)

        #remove all existing curtain
        Curtain.objects.all().delete()

        with transaction.atomic():
            for d in data:
                curtain = Curtain.objects.create(
                    id=d["pk"],
                    created=d["fields"]["created"],
                    link_id=d["fields"]["link_id"],
                    description=d["fields"]["description"],
                    enable=d["fields"]["enable"],
                    curtain_type=d["fields"]["curtain_type"],
                )
                curtain.file = d["fields"]["file"]
                for owner in d["fields"]["owners"]:
                    print(owner)
                    curtain.owners.add(User.objects.get(id=owner))
                curtain.save()
