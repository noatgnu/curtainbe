import uuid

from django.db import models
from django.contrib.auth.models import User
from rest_framework_api_key.crypto import KeyGenerator

from curtainbe import settings
from rest_framework_api_key.models import AbstractAPIKey, BaseAPIKeyManager


class ExtraProperties(models.Model):
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
    key_generator = KeyGenerator(prefix_length=16, secret_key_length=128)

class UserAPIKey(AbstractAPIKey):
    objects = UserAPIKeyManager()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    can_read = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)



class UserPublicKey(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="public_keys")
    public_key = models.BinaryField()


class Curtain(models.Model):
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
    name = models.TextField()


class DataFilterList(models.Model):
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
    entry = models.TextField()
    position = models.IntegerField()
    residue = models.CharField(
        max_length=1
    )
    data = models.TextField()


class CurtainAccessToken(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.CASCADE, related_name="access_token",
        blank=True,
        null=True
    )
    token = models.TextField()


class DataAESEncryptionFactors(models.Model):
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
    created = models.DateTimeField(auto_now_add=True)
    curtain = models.ForeignKey(
        "Curtain", on_delete=models.CASCADE, related_name="data_hash",
        blank=True,
        null=True
    )
    hash = models.TextField()

