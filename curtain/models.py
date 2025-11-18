import uuid

from django.core.mail import send_mail
from django.db import models
from django.contrib.auth.models import User
from rest_framework_api_key.crypto import KeyGenerator

from curtainbe import settings
from rest_framework_api_key.models import AbstractAPIKey, BaseAPIKeyManager
from curtain.storage import DataCiteLocalStorage


class ExtraProperties(models.Model):
    """
    This model represents additional properties for a user. It includes fields for curtain link limits,
    social platform, curtain link limit exceed flag, curtain post flag, and a default public key.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    curtain_link_limits = models.IntegerField(default=settings.CURTAIN_DEFAULT_USER_LINK_LIMIT)
    social_platform = models.ForeignKey("SocialPlatform", on_delete=models.SET_NULL,
                                        related_name="user_social_platform",
                                        blank=True,
                                        null=True)
    curtain_link_limit_exceed = models.BooleanField(default=False)
    curtain_post = models.BooleanField(default=settings.CURTAIN_DEFAULT_USER_CAN_POST)
    default_public_key = models.ForeignKey("UserPublicKey", on_delete=models.SET_NULL, blank=True, null=True,
                                           related_name="user_default_public_key")


class UserAPIKeyManager(BaseAPIKeyManager):

    key_generator = KeyGenerator(prefix_length=8, secret_key_length=128)

class UserAPIKey(AbstractAPIKey):
    """
    This model represents an API key for a user. It includes fields for read, create, delete, and update permissions.
    """
    objects = UserAPIKeyManager()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    can_read = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)



class UserPublicKey(models.Model):
    """
    This model represents a public key for a user.
    """
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="public_keys")
    public_key = models.BinaryField()


class Curtain(models.Model):
    """
    This model represents a Curtain, which includes fields for creation and update timestamps, a unique link ID,
    a file, a description, owners, enable flag, curtain type, and an encrypted flag.
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    link_id = models.TextField(unique=True, default=uuid.uuid4, null=False)
    file = models.FileField(upload_to="media/files/curtain_upload/")
    description = models.TextField()
    owners = models.ManyToManyField(User, related_name="curtain")
    enable = models.BooleanField(default=True)
    curtain_type_choices = [
        ("TP", "Total Proteomics"),
        ("PTM", "Post-translational Modification"),
        ("F", "Flex")
    ]

    curtain_type = models.CharField(
        max_length=3,
        choices=curtain_type_choices,
        default="TP"
    )
    permanent = models.BooleanField(default=True)
    encrypted = models.BooleanField(default=False)

    def __str__(self):
        owners = "None"
        if self.owners:
            owners = ",".join([i.username for i in self.owners.all()])
        return f"{self.link_id} - {self.curtain_type} - Created: {self.created} - owners: {owners}"

    def __repr__(self):
        owners = "None"
        if self.owners:
            owners = ",".join([i.username for i in self.owners.all()])
        return f"{self.link_id} - {self.curtain_type} - Created: {self.created} - owners: {owners}"

class SocialPlatform(models.Model):
    """
    This model represents a social platform with a name field.
    """
    name = models.TextField()


class DataFilterList(models.Model):
    """
    This model represents a data filter list, which includes fields for name, category, data, default flag, and a user.
    """
    name = models.TextField()
    category = models.TextField()
    data = models.TextField()
    default = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="users", blank=True, null=True)

    def __repr__(self):
        return f"{self.name} - {self.category} - {self.user}"

    def __str__(self):
        return f"{self.name} - {self.category} - {self.user}"


class KinaseLibraryModel(models.Model):
    """
    This model represents a kinase library model, which includes fields for entry, position, residue, and data.
    """
    entry = models.TextField()
    position = models.IntegerField()
    residue = models.CharField(
        max_length=1
    )
    data = models.TextField()


class CurtainAccessToken(models.Model):
    """
    This model represents an access token for a Curtain.
    """
    created = models.DateTimeField(auto_now_add=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.CASCADE, related_name="access_token",
        blank=True,
        null=True
    )
    token = models.TextField()


class DataAESEncryptionFactors(models.Model):
    """
    This model represents AES encryption factors for a Curtain, which includes fields for an encrypted decryption key,
    an encrypted IV, and a reference to the public key used for encryption.
    """
    created = models.DateTimeField(auto_now_add=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.CASCADE, related_name="encryption_factors",
        blank=True,
        null=True
    )
    encrypted_decryption_key = models.TextField()
    encrypted_iv = models.TextField()
    encrypted_with = models.ForeignKey("UserPublicKey", on_delete=models.SET_NULL, blank=True, null=True, related_name="encrypted_with")

class DataHash(models.Model):
    """
    This model represents a data hash for a Curtain.
    """
    created = models.DateTimeField(auto_now_add=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.CASCADE, related_name="data_hash",
        blank=True,
        null=True
    )
    hash = models.TextField()

class DataCite(models.Model):
    """
    This model represents a data citation for a Curtain.
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    status_choices = [
        ("pending", "Pending"),
        ("published", "Published"),
        ("draft", "Draft"),
        ("rejected", "Rejected")
    ]
    status = models.CharField(max_length=10, choices=status_choices, default="pending")
    lock = models.BooleanField(default=True)
    doi = models.TextField(blank=True, null=True)
    title = models.TextField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="data_cite", blank=True, null=True)
    form_data = models.JSONField(blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    pii_statement = models.TextField(blank=True, null=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.SET_NULL, related_name="data_cite",
        blank=True,
        null=True
    )
    local_file = models.FileField(
        upload_to="datacite_files/",
        storage=DataCiteLocalStorage,
        blank=True,
        null=True,
        help_text="Local file storage for DataCite data (stored on host, not cloud)"
    )

    class Meta:
        ordering = ["-updated"]

    def send_notification(self):
        send_mail(
            'Curtain Data Cite Notification',
            f'Your data cite request has been processed and the status of {self.doi} is now {self.status}.',
            settings.NOTIFICATION_EMAIL_FROM,
            [self.contact_email],
            fail_silently=False,
        )

class LastAccess(models.Model):
    """
    This model represents the last access timestamp for a Curtain.
    """
    curtain = models.ForeignKey(Curtain, on_delete=models.CASCADE, related_name="last_access")
    last_access = models.DateTimeField(auto_now=True)

