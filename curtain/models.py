import uuid
from datetime import timedelta

from django.core.mail import send_mail
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework_api_key.crypto import KeyGenerator

from curtainbe import settings
from rest_framework_api_key.models import AbstractAPIKey, BaseAPIKeyManager
from curtain.storage import DataCiteLocalStorage


def get_default_expiry_duration():
    """
    Returns the default expiry duration (3 months)
    """
    return timedelta(days=90)


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
    a file, a description, owners, enable flag, curtain type, encrypted flag, and expiry date.
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
    expiry_duration = models.DurationField(default=get_default_expiry_duration, null=False)

    @property
    def is_expired(self):
        """
        Check if the curtain has expired based on last access and expiry duration.
        Returns False if permanent is True.
        Returns True if (last_access + expiry_duration) < now.
        """
        if self.permanent:
            return False

        last_access_record = self.last_access.order_by('-last_access').first()
        if last_access_record:
            expiry_time = last_access_record.last_access + self.expiry_duration
            return timezone.now() > expiry_time

        expiry_time = self.created + self.expiry_duration
        return timezone.now() > expiry_time

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
    collection = models.ForeignKey(
        "CurtainCollection", on_delete=models.SET_NULL, related_name="data_cite",
        blank=True,
        null=True,
        help_text="Optional collection - if set, all curtain sessions in collection will be included as relatedIdentifiers"
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


class Announcement(models.Model):
    """
    This model represents system announcements that can be displayed to users.
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    ANNOUNCEMENT_TYPE_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('success', 'Success'),
        ('error', 'Error'),
        ('maintenance', 'Maintenance'),
    ]

    title = models.CharField(max_length=255)
    content = models.TextField()
    announcement_type = models.CharField(max_length=20, choices=ANNOUNCEMENT_TYPE_CHOICES, default='info')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    starts_at = models.DateTimeField(null=True, blank=True, help_text="When to start showing this announcement")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When to stop showing this announcement")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="announcements")
    show_on_login = models.BooleanField(default=False, help_text="Show this announcement on login page")
    dismissible = models.BooleanField(default=True, help_text="Can users dismiss this announcement")

    class Meta:
        ordering = ['-priority', '-created']

    def __str__(self):
        return f"{self.title} ({self.announcement_type} - {self.priority})"

    @property
    def is_visible(self):
        """
        Check if announcement should be visible based on is_active and date range.
        """
        if not self.is_active:
            return False

        now = timezone.now()

        if self.starts_at and now < self.starts_at:
            return False

        if self.expires_at and now > self.expires_at:
            return False

        return True


class PermanentLinkRequest(models.Model):
    """
    This model represents a request from a user to make their curtain session permanent
    or extend the expiry duration.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    REQUEST_TYPE_CHOICES = [
        ('permanent', 'Make Permanent'),
        ('extend', 'Extend Expiry Duration'),
    ]

    curtain = models.ForeignKey(Curtain, on_delete=models.CASCADE, related_name="permanent_requests")
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permanent_link_requests")
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES, default='permanent', help_text="Type of request: permanent or extend")
    requested_expiry_months = models.IntegerField(null=True, blank=True, help_text="Requested expiry duration in months (for extend requests)")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reason = models.TextField(blank=True, null=True, help_text="User's reason for requesting permanent link or extension")
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_permanent_requests")
    admin_notes = models.TextField(blank=True, null=True, help_text="Admin's notes on the request")

    class Meta:
        ordering = ['-requested_at']
        unique_together = ['curtain', 'requested_by', 'status']

    def __str__(self):
        if self.request_type == 'permanent':
            return f"Permanent link request for {self.curtain.link_id} by {self.requested_by.username} - {self.status}"
        else:
            return f"Expiry extension request ({self.requested_expiry_months} months) for {self.curtain.link_id} by {self.requested_by.username} - {self.status}"

    def approve(self, admin_user):
        """
        Approve the request and make the curtain permanent or extend expiry duration.
        """
        self.status = 'approved'
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()

        curtain = Curtain.objects.get(id=self.curtain.id)
        if self.request_type == 'permanent':
            curtain.permanent = True
            curtain.save(update_fields=['permanent'])
        elif self.request_type == 'extend' and self.requested_expiry_months:
            curtain.expiry_duration = timedelta(days=self.requested_expiry_months * 30)
            curtain.save(update_fields=['expiry_duration'])

    def reject(self, admin_user, notes=None):
        """
        Reject the request.
        """
        self.status = 'rejected'
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        if notes:
            self.admin_notes = notes
        self.save()


class CurtainCollection(models.Model):
    """
    Model representing a collection of curtain sessions grouped together by a user.
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="curtain_collections")
    curtains = models.ManyToManyField(Curtain, related_name="collections", blank=True)

    class Meta:
        ordering = ['-updated']

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

