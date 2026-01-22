import hashlib
import mimetypes
import os
from typing import List, Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser

from drf_chunked_upload.models import AbstractChunkedUpload
from drf_chunked_upload.serializers import ChunkedUploadSerializer
from drf_chunked_upload.views import ChunkedUploadView
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from curtain.models import Curtain
from curtain.serializers import CurtainSerializer
from curtain.permissions import IsNonUserPostAllow
from rest_framework import permissions


class CurtainChunkedUpload(AbstractChunkedUpload):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="curtain_chunked_uploads",
        editable=False,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Original filename as provided by client",
    )
    mime_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Detected MIME type of the uploaded file",
    )
    file_size = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="Total size of the uploaded file in bytes",
    )
    upload_session_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Session ID for tracking related uploads",
    )

    class Meta:
        app_label = "curtain"

    def append_chunk(self, chunk, chunk_size=None, save=True):
        """
        Override append_chunk to handle S3 and other remote storage backends properly.

        For remote storage (S3, GCS), we accumulate chunks in a local temporary file
        and upload when complete to avoid reading/writing the entire file on each chunk.
        """
        self.offset += chunk_size or len(chunk)

        # Check if using remote storage
        is_remote_storage = (
            hasattr(self.file.storage, 'bucket') or
            hasattr(self.file.storage, 'client') or
            'S3' in str(type(self.file.storage)) or
            'GCS' in str(type(self.file.storage)) or
            'GoogleCloud' in str(type(self.file.storage))
        )

        if is_remote_storage:
            # For remote storage, use a local temporary file approach
            import tempfile

            # Get or create temp file path
            temp_dir = os.path.join(settings.BASE_DIR, 'temp_uploads')
            os.makedirs(temp_dir, exist_ok=True)

            # Use upload ID as temp filename
            temp_filename = f"temp_{self.id}.tmp"
            temp_path = os.path.join(temp_dir, temp_filename)

            # Append chunk to local temp file
            with open(temp_path, 'ab') as temp_file:
                temp_file.write(chunk)

            # Store the temp path for later upload
            self._temp_upload_path = temp_path
        else:
            # Local file system - open file in append mode
            try:
                self.file.open(mode='ab')
                self.file.write(chunk)
            finally:
                self.file.close()

        if save:
            self.save()

    def save(self, *args, **kwargs):
        if not self.original_filename and self.filename:
            self.original_filename = self.filename

        if self.filename and not self.mime_type:
            self.mime_type, _ = mimetypes.guess_type(self.filename)

        # Handle upload completion for remote storage
        if self.status == self.COMPLETE and hasattr(self, '_temp_upload_path'):
            temp_path = self._temp_upload_path
            if os.path.exists(temp_path):
                # Upload the temp file to remote storage
                with open(temp_path, 'rb') as temp_file:
                    filename = self.filename or self.generate_filename()
                    from django.core.files.base import ContentFile
                    self.file.save(filename, ContentFile(temp_file.read()), save=False)

                # Clean up temp file
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if self.status == self.COMPLETE and self.file and not self.file_size:
            try:
                # For remote storage, get size differently
                if hasattr(self.file, 'size'):
                    self.file_size = self.file.size
                elif hasattr(self.file, 'path') and os.path.exists(self.file.path):
                    self.file_size = os.path.getsize(self.file.path)
            except (OSError, ValueError, AttributeError):
                pass

        super().save(*args, **kwargs)

    def generate_filename(self):
        if self.file:
            sha256_hash = hashlib.sha256()
            self.file.seek(0)
            for chunk in iter(lambda: self.file.read(4096), b""):
                sha256_hash.update(chunk)
            self.file.seek(0)

            hash_prefix = sha256_hash.hexdigest()[:16]
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            user_id = self.user.id if self.user else "anonymous"

            original_ext = ""
            if self.original_filename or self.filename:
                source_name = self.original_filename or self.filename
                original_ext = os.path.splitext(source_name)[1].lower()

            return f"curtain_{user_id}_{hash_prefix}_{timestamp}{original_ext}"

        import uuid
        return f"curtain_{uuid.uuid4().hex[:8]}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

    def verify_integrity(self, expected_checksum: str = None) -> bool:
        if not self.file or not os.path.exists(self.file.path):
            return False

        calculated_checksum = self.checksum
        if not calculated_checksum:
            return False

        if expected_checksum:
            return calculated_checksum == expected_checksum

        return True

    def get_allowed_extensions(self) -> List[str]:
        return [".json"]

    def get_allowed_mime_types(self) -> List[str]:
        return [
            "application/json",
            "text/json",
            "text/plain"
        ]

    def validate_file_type(self) -> Tuple[bool, str]:
        if not self.filename:
            return True, ""

        allowed_extensions = self.get_allowed_extensions()
        allowed_mime_types = self.get_allowed_mime_types()

        if not allowed_extensions and not allowed_mime_types:
            return True, ""

        file_ext = os.path.splitext(self.filename.lower())[1]
        if allowed_extensions and file_ext not in allowed_extensions:
            return (
                False,
                f"Unsupported file extension: {file_ext}. Allowed: {', '.join(allowed_extensions)}",
            )

        if allowed_mime_types and self.mime_type and self.mime_type not in allowed_mime_types:
            return (
                False,
                f"Unsupported MIME type: {self.mime_type}. Allowed: {', '.join(allowed_mime_types)}",
            )

        return True, ""

    def get_max_file_size(self) -> Optional[int]:
        return getattr(settings, "DRF_CHUNKED_UPLOAD_MAX_BYTES", None)

    def validate_file_size(self) -> Tuple[bool, str]:
        max_size = self.get_max_file_size()
        if not max_size or not self.file_size:
            return True, ""

        if self.file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            return (
                False,
                (
                    f"File size ({self.file_size / (1024 * 1024):.1f} MB) "
                    f"exceeds maximum allowed size ({max_size_mb:.1f} MB)"
                ),
            )

        return True, ""

    def validate_upload(self) -> Tuple[bool, str]:
        is_valid, error_msg = self.validate_file_type()
        if not is_valid:
            return is_valid, error_msg

        is_valid, error_msg = self.validate_file_size()
        if not is_valid:
            return is_valid, error_msg

        return True, ""


class CurtainChunkedUploadSerializer(ChunkedUploadSerializer):
    class Meta:
        model = CurtainChunkedUpload
        fields = (
            "id",
            "file",
            "filename",
            "offset",
            "created_at",
            "status",
            "completed_at",
            "original_filename",
            "mime_type",
            "file_size",
            "upload_session_id",
        )
        read_only_fields = (
            "id",
            "created_at",
            "status",
            "completed_at",
            "mime_type",
            "file_size",
        )


class CurtainChunkedUploadView(ChunkedUploadView):
    model = CurtainChunkedUpload
    serializer_class = CurtainChunkedUploadSerializer
    permission_classes = [permissions.IsAdminUser | IsNonUserPostAllow]
    parser_classes = [MultiPartParser]

    def on_completion(self, uploaded_file, request):
        try:
            curtain_id = request.data.get("curtain_id")
            link_id = request.data.get("link_id")
            is_update = curtain_id or link_id

            if is_update:
                if curtain_id:
                    c = Curtain.objects.filter(id=curtain_id).first()
                else:
                    c = Curtain.objects.filter(link_id=link_id).first()

                if not c:
                    return Response(
                        data={"error": "Curtain session not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )

                if type(request.user) == AnonymousUser or request.user not in c.owners.all():
                    return Response(
                        data={"error": "You do not have permission to update this curtain"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                c = Curtain()

            description = request.data.get("description", "" if not is_update else c.description)
            enable = request.data.get("enable", "True" if not is_update else str(c.enable)) == "True"
            curtain_type = request.data.get("curtain_type", "TP" if not is_update else c.curtain_type)
            permanent = request.data.get("permanent", "True" if not is_update else str(c.permanent)) == "True"
            encrypted = request.data.get("encrypted", "False" if not is_update else str(c.encrypted)) == "True"
            expiry_duration = request.data.get("expiry_duration")

            if permanent and not settings.CURTAIN_ALLOW_USER_SET_PERMANENT and not request.user.is_staff:
                return Response(
                    data={"error": "Only staff users can set permanent to True"},
                    status=status.HTTP_403_FORBIDDEN
                )

            if uploaded_file.file:
                c.file = uploaded_file.file

            c.description = description
            c.enable = enable
            c.curtain_type = curtain_type
            c.permanent = permanent
            c.encrypted = encrypted

            if expiry_duration:
                from datetime import timedelta
                expiry_months = int(expiry_duration)
                if expiry_months not in [3, 6]:
                    if not request.user.is_staff:
                        return Response(
                            data={"error": "expiry_duration must be 3 or 6 months"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                c.expiry_duration = timedelta(days=expiry_months * 30)

            c.save()

            if not is_update:
                if type(request.user) != AnonymousUser:
                    c.owners.add(request.user)

                    if settings.CURTAIN_DEFAULT_USER_LINK_LIMIT != 0:
                        total_count = request.user.curtain.count()
                        request.user.extraproperties.curtain_link_limit_exceed = (
                            total_count >= settings.CURTAIN_DEFAULT_USER_LINK_LIMIT
                        )
                    else:
                        request.user.extraproperties.curtain_link_limit_exceed = False
                    request.user.extraproperties.save()

            curtain_json = CurtainSerializer(c, many=False, context={"request": request})

            uploaded_file.delete()

            result = {
                "curtain": curtain_json.data,
                "message": "Curtain session updated successfully from chunked upload" if is_update else "Curtain session created successfully from chunked upload",
            }
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create curtain from chunked upload: {str(e)}")
            result = {
                "error": f"File uploaded but curtain creation failed: {str(e)}"
            }
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
