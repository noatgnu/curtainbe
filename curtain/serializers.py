import json
import os

from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers
from django.urls import reverse

from curtain.models import Curtain, KinaseLibraryModel, DataFilterList, UserPublicKey, UserAPIKey, \
    DataAESEncryptionFactors, DataHash, LastAccess, DataCite, Announcement, PermanentLinkRequest, CurtainCollection
from curtainbe import settings
from django.contrib.auth.models import User



class UserSerializer(FlexFieldsModelSerializer):
    project = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    curtain = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    can_delete = serializers.SerializerMethodField()

    def get_can_delete(self, user):
        if settings.CURTAIN_ALLOW_NON_STAFF_DELETE:
            return True
        else:
            return user.is_staff

    class Meta:
        model = User
        fields = ["id", "username", "is_staff", "is_authenticated", "project", "curtain", "can_delete"]
        expandable_fields = dict(
            project=("celsus.serializers.ProjectSerializer",
                            dict(many=True, read_only=True)),
            curtain=(
            "celsus.serializers.CurtainSerializer", dict(fields=["id", "description"], many=True, read_only=True))
        )


class CurtainSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()
    data_cite = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    last_access_date = serializers.SerializerMethodField()
    expiry_duration_months = serializers.SerializerMethodField()

    def get_file(self, record):
        _, filename = os.path.split(record.file.name)
        return filename

    def get_data_cite(self, record):
        data_cite = DataCite.objects.filter(curtain=record)
        if data_cite.exists():
            return DataCiteSerializer(data_cite.first()).data
        else:
            return None

    def get_is_expired(self, record):
        return record.is_expired

    def get_last_access_date(self, record):
        last_access_record = record.last_access.order_by('-last_access').first()
        if last_access_record:
            return last_access_record.last_access
        return None

    def get_expiry_duration_months(self, record):
        return int(record.expiry_duration.days / 30)

    class Meta:
        model = Curtain
        fields = ["id", "created", "link_id", "file", "enable", "description", "curtain_type", "encrypted", "permanent", "expiry_duration_months", "is_expired", "last_access_date", "data_cite"]
        lookup_field = "link_id"


class KinaseLibrarySerializer(FlexFieldsModelSerializer):
    data = serializers.SerializerMethodField()

    def get_data(self, kinase_library):
        return json.loads(kinase_library.data)
    class Meta:
        model = KinaseLibraryModel
        fields = ["id", "entry", "position", "residue", "data"]

class DataFilterListSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = DataFilterList
        fields = ["id", "name", "data", "default"]


class UserPublicKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPublicKey
        fields = ["id", "public_key"]


class UserAPIKeySerializer(serializers.ModelSerializer):

    class Meta:
        model = UserAPIKey
        fields = ["id", "name", "can_read", "can_create", "can_delete", "can_update"]


class DataAESEncryptionFactorsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataAESEncryptionFactors
        fields = ["id", "encrypted_decryption_key", "encrypted_iv", "encrypted_with"]


class DataHashSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataHash
        fields = ["id", "hash", "hash"]

class LastAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = LastAccess
        fields = ["id", "last_access", "curtain"]

class DataCiteSerializer(serializers.ModelSerializer):
    curtain = serializers.SerializerMethodField()
    curtain_type = serializers.SerializerMethodField()
    local_file = serializers.FileField(read_only=True)
    public_file_url = serializers.SerializerMethodField()

    def get_curtain(self, data_cite):
        if data_cite.curtain:
            return data_cite.curtain.link_id
        else:
            return None

    def get_curtain_type(self, data_cite):
        if data_cite.curtain:
            return data_cite.curtain.curtain_type
        else:
            return None

    def get_public_file_url(self, data_cite):
        if data_cite.local_file:
            file_path = reverse('datacite_file', kwargs={'datacite_id': data_cite.id})
            if settings.SITE_DOMAIN:
                return f"{settings.SITE_DOMAIN.rstrip('/')}{file_path}"
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(file_path)
            return file_path
        return None

    class Meta:
        model = DataCite
        fields = ["id", "updated", "created", "curtain", "curtain_type", "doi", "status", "user", "title", "form_data", "contact_email", "pii_statement", "lock", "local_file", "public_file_url"]


class AnnouncementSerializer(serializers.ModelSerializer):
    is_visible = serializers.SerializerMethodField()
    created_by_username = serializers.SerializerMethodField()

    def get_is_visible(self, announcement):
        return announcement.is_visible

    def get_created_by_username(self, announcement):
        if announcement.created_by:
            return announcement.created_by.username
        return None

    class Meta:
        model = Announcement
        fields = ["id", "title", "content", "announcement_type", "priority", "is_active", "created", "updated",
                  "starts_at", "expires_at", "created_by_username", "show_on_login", "dismissible", "is_visible"]
        read_only_fields = ["id", "created", "updated", "is_visible", "created_by_username"]


class PermanentLinkRequestSerializer(serializers.ModelSerializer):
    curtain_link_id = serializers.SerializerMethodField()
    requested_by_username = serializers.SerializerMethodField()
    reviewed_by_username = serializers.SerializerMethodField()

    def get_curtain_link_id(self, request):
        return request.curtain.link_id

    def get_requested_by_username(self, request):
        return request.requested_by.username

    def get_reviewed_by_username(self, request):
        if request.reviewed_by:
            return request.reviewed_by.username
        return None

    class Meta:
        model = PermanentLinkRequest
        fields = ["id", "curtain", "curtain_link_id", "requested_by", "requested_by_username", "request_type",
                  "requested_expiry_months", "status", "reason", "requested_at", "reviewed_at", "reviewed_by",
                  "reviewed_by_username", "admin_notes"]
        read_only_fields = ["id", "requested_by", "requested_at", "reviewed_at", "reviewed_by", "curtain_link_id",
                            "requested_by_username", "reviewed_by_username"]


class CurtainCollectionSerializer(serializers.ModelSerializer):
    """
    Serializer for CurtainCollection model.
    """
    owner_username = serializers.SerializerMethodField()
    curtain_count = serializers.SerializerMethodField()
    accessible_curtains = serializers.SerializerMethodField()

    def get_owner_username(self, collection):
        return collection.owner.username

    def get_curtain_count(self, collection):
        return collection.curtains.count()

    def get_accessible_curtains(self, collection):
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None
        curtain_type = request.query_params.get('curtain_type') if request else None

        accessible = []
        for curtain in collection.curtains.all():
            if curtain_type and curtain.curtain_type != curtain_type:
                continue

            if curtain.enable:
                accessible.append({
                    "id": curtain.id,
                    "link_id": curtain.link_id,
                    "description": curtain.description,
                    "created": curtain.created,
                    "curtain_type": curtain.curtain_type,
                })
            elif user and (curtain.owners.filter(id=user.id).exists() or user.is_staff):
                accessible.append({
                    "id": curtain.id,
                    "link_id": curtain.link_id,
                    "description": curtain.description,
                    "created": curtain.created,
                    "curtain_type": curtain.curtain_type,
                })
        return accessible

    class Meta:
        model = CurtainCollection
        fields = ["id", "created", "updated", "name", "description", "enable", "owner", "owner_username",
                  "curtains", "curtain_count", "accessible_curtains"]
        read_only_fields = ["id", "created", "updated", "owner", "owner_username", "curtain_count", "accessible_curtains"]