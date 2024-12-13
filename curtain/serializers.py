import json
import os

from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from curtain.models import Curtain, KinaseLibraryModel, DataFilterList, UserPublicKey, UserAPIKey, \
    DataAESEncryptionFactors, DataHash, LastAccess, DataCite
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

    def get_file(self, record):
        _, filename = os.path.split(record.file.name)
        return filename

    def get_data_cite(self, record):
        data_cite = DataCite.objects.filter(curtain=record)
        if data_cite.exists():
            return DataCiteSerializer(data_cite.first()).data
        else:
            return None

    class Meta:
        model = Curtain
        fields = ["id", "created", "link_id", "file", "enable", "description", "curtain_type", "encrypted", "permanent", "data_cite"]
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

    def get_curtain(self, data_cite):
        if data_cite.curtain:
            return data_cite.curtain.link_id
        else:
            return None

    class Meta:
        model = DataCite
        fields = ["id", "updated", "created", "curtain", "doi", "status", "user", "title", "form_data", "contact_email", "pii_statement", "lock"]