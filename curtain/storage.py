from django.core.files.storage import FileSystemStorage
from django.conf import settings


class DataCiteLocalStorage(FileSystemStorage):
    """
    Custom storage backend for DataCite files that always uses local file system storage,
    regardless of the default storage backend configuration.
    """
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.BASE_DIR / 'media' / 'datacite'
        kwargs['base_url'] = '/media/datacite/'
        super().__init__(*args, **kwargs)
