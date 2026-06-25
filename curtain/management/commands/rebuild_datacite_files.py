from django.core.management.base import BaseCommand, CommandError
from curtain.models import DataCite


class Command(BaseCommand):
    help = 'Rebuild local files and collection metadata JSON for DataCite objects'

    def add_arguments(self, parser):
        parser.add_argument(
            'datacite_ids',
            nargs='*',
            type=int,
            help='Specific DataCite IDs to rebuild files for',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Rebuild all DataCite objects',
        )
        parser.add_argument(
            '--update-doi',
            action='store_true',
            help='Also sync and update the DOI metadata on the DataCite REST API',
        )

    def handle(self, *args, **options):
        datacite_ids = options['datacite_ids']
        rebuild_all = options['all']
        update_doi = options['update_doi']

        if not datacite_ids and not rebuild_all:
            raise CommandError('You must specify either one or more datacite_ids or use the --all flag.')

        if rebuild_all:
            queryset = DataCite.objects.all()
        else:
            queryset = DataCite.objects.filter(id__in=datacite_ids)

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No DataCite objects found matching the criteria.'))
            return

        self.stdout.write(f'Starting rebuild of local files for {total} DataCite object(s)...')

        success_count = 0
        error_count = 0

        for datacite in queryset:
            try:
                self.stdout.write(f'Processing DataCite ID: {datacite.id} (DOI: {datacite.doi or "Draft"})...')
                datacite.rebuild_local_files(update_doi_api=update_doi)
                self.stdout.write(self.style.SUCCESS(f'Successfully rebuilt files for DataCite ID: {datacite.id}'))
                success_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error rebuilding files for DataCite ID: {datacite.id}: {e}'))
                error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Finished rebuilding DataCite files. Successes: {success_count}, Errors: {error_count}'
            )
        )
