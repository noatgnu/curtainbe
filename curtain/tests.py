from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import TimestampSigner
from django.urls import reverse
from django.test import override_settings
from django.core.management import call_command
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
from curtain.models import ExtraProperties, SocialPlatform, UserPublicKey, Curtain, CurtainCollection, DataCite
from curtain.admin import DataCiteAdmin
from curtainbe import settings


class ExtraPropertiesModelTest(TestCase):
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.social_platform = SocialPlatform.objects.create(name='Twitter')
        self.public_key = UserPublicKey.objects.create(
            user=self.user,
            public_key=b'test_public_key_data'
        )

    def test_create_extra_properties_with_defaults(self):
        """Test creating ExtraProperties with default values."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        
        self.assertEqual(extra_props.user, self.user)
        self.assertEqual(extra_props.curtain_link_limits, settings.CURTAIN_DEFAULT_USER_LINK_LIMIT)
        self.assertIsNone(extra_props.social_platform)
        self.assertFalse(extra_props.curtain_link_limit_exceed)
        self.assertEqual(extra_props.curtain_post, settings.CURTAIN_DEFAULT_USER_CAN_POST)
        self.assertIsNone(extra_props.default_public_key)

    def test_create_extra_properties_with_custom_values(self):
        """Test creating ExtraProperties with custom values."""
        extra_props = ExtraProperties.objects.create(
            user=self.user,
            curtain_link_limits=10,
            social_platform=self.social_platform,
            curtain_link_limit_exceed=True,
            curtain_post=False,
            default_public_key=self.public_key
        )
        
        self.assertEqual(extra_props.user, self.user)
        self.assertEqual(extra_props.curtain_link_limits, 10)
        self.assertEqual(extra_props.social_platform, self.social_platform)
        self.assertTrue(extra_props.curtain_link_limit_exceed)
        self.assertFalse(extra_props.curtain_post)
        self.assertEqual(extra_props.default_public_key, self.public_key)

    def test_one_to_one_relationship_with_user(self):
        """Test that ExtraProperties has a OneToOne relationship with User."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        
        # Verify the relationship
        self.assertEqual(self.user.extraproperties, extra_props)
        
        # Verify that creating another ExtraProperties for the same user raises IntegrityError
        with self.assertRaises(IntegrityError):
            ExtraProperties.objects.create(user=self.user)

    def test_user_deletion_cascades(self):
        """Test that deleting a user deletes the associated ExtraProperties."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        extra_props_id = extra_props.pk
        
        # Delete the user
        self.user.delete()
        
        # Verify ExtraProperties is also deleted
        with self.assertRaises(ExtraProperties.DoesNotExist):
            ExtraProperties.objects.get(pk=extra_props_id)

    def test_social_platform_set_null_on_delete(self):
        """Test that deleting a social platform sets the field to null."""
        extra_props = ExtraProperties.objects.create(
            user=self.user,
            social_platform=self.social_platform
        )
        
        # Delete the social platform
        self.social_platform.delete()
        
        # Refresh from database and verify social_platform is null
        extra_props.refresh_from_db()
        self.assertIsNone(extra_props.social_platform)

    def test_default_public_key_set_null_on_delete(self):
        """Test that deleting a public key sets the field to null."""
        extra_props = ExtraProperties.objects.create(
            user=self.user,
            default_public_key=self.public_key
        )
        
        # Delete the public key
        self.public_key.delete()
        
        # Refresh from database and verify default_public_key is null
        extra_props.refresh_from_db()
        self.assertIsNone(extra_props.default_public_key)

    def test_user_as_primary_key(self):
        """Test that user field serves as the primary key."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        
        # The primary key should be the user's pk
        self.assertEqual(extra_props.pk, self.user.pk)

    def test_field_defaults_match_settings(self):
        """Test that field defaults match the values from settings."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        
        self.assertEqual(extra_props.curtain_link_limits, settings.CURTAIN_DEFAULT_USER_LINK_LIMIT)
        self.assertEqual(extra_props.curtain_post, settings.CURTAIN_DEFAULT_USER_CAN_POST)

    def test_boolean_fields_default_values(self):
        """Test boolean fields have correct default values."""
        extra_props = ExtraProperties.objects.create(user=self.user)
        
        self.assertFalse(extra_props.curtain_link_limit_exceed)
        self.assertEqual(extra_props.curtain_post, settings.CURTAIN_DEFAULT_USER_CAN_POST)

    def test_nullable_fields_can_be_none(self):
        """Test that nullable fields can be set to None."""
        extra_props = ExtraProperties.objects.create(
            user=self.user,
            social_platform=None,
            default_public_key=None
        )
        
        self.assertIsNone(extra_props.social_platform)
        self.assertIsNone(extra_props.default_public_key)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class DataCiteViewSetsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Create curtains
        self.main_file = SimpleUploadedFile("main.txt", b"main session content")
        self.alt_file = SimpleUploadedFile("alt.txt", b"alternative session content")
        
        self.main_curtain = Curtain.objects.create(
            name="Main Session",
            description="Main session description",
            file=self.main_file,
            enable=True
        )
        self.main_curtain.owners.add(self.user)
        
        self.alt_curtain = Curtain.objects.create(
            name="Alternative Session",
            description="Alternative session description",
            file=self.alt_file,
            enable=True
        )
        self.alt_curtain.owners.add(self.user)
        
        # Create collection
        self.collection = CurtainCollection.objects.create(
            name="Test Collection",
            description="Collection description",
            owner=self.user,
            enable=True
        )
        self.collection.curtains.add(self.main_curtain, self.alt_curtain)

    @patch('curtain.view_sets.DataCiteRESTClient')
    @patch('curtain.view_sets.schema45')
    def test_create_datacite_with_collection_associated(self, mock_schema, mock_client_class):
        # Setup mocks
        mock_schema.validate.return_value = True
        mock_client = MagicMock()
        mock_client.draft_doi.return_value = "10.5072/test-doi-suffix"
        mock_client_class.return_value = mock_client
        
        # Generate token
        signer = TimestampSigner()
        token = signer.sign("test-doi-suffix")
        
        # Post payload
        payload = {
            "contact_email": "test@example.com",
            "pii_statement": "No PII is present in this data.",
            "token": token,
            "linkID": str(self.main_curtain.link_id),
            "form": {
                "titles": [{"title": "My Dataset"}],
                "suffix": "test-doi-suffix"
            }
        }
        
        url = reverse('datacite-list')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["collection"], self.collection.id)
        
        # Verify alternate identifiers in form_data contains alternative session and metadata
        datacite_obj = DataCite.objects.get(id=response.data["id"])
        self.assertEqual(datacite_obj.collection, self.collection)
        
        alternate_ids = datacite_obj.form_data["alternateIdentifiers"]
        alternate_id_types = [item["alternateIdentifierType"] for item in alternate_ids]
        
        self.assertIn("Curtain Main Session Data", alternate_id_types)
        self.assertIn("Curtain Alternative Session Data", alternate_id_types)
        self.assertIn("Curtain Collection Metadata", alternate_id_types)

    @patch('curtain.view_sets.DataCiteRESTClient')
    @patch('curtain.view_sets.schema45')
    def test_create_datacite_with_explicit_collection_id(self, mock_schema, mock_client_class):
        # Setup mocks
        mock_schema.validate.return_value = True
        mock_client = MagicMock()
        mock_client.draft_doi.return_value = "10.5072/test-doi-suffix-explicit"
        mock_client_class.return_value = mock_client
        
        # Generate token
        signer = TimestampSigner()
        token = signer.sign("test-doi-suffix-explicit")
        
        # Post payload with explicit collection_id
        payload = {
            "contact_email": "test@example.com",
            "pii_statement": "No PII is present in this data.",
            "token": token,
            "linkID": str(self.main_curtain.link_id),
            "collection_id": self.collection.id,
            "form": {
                "titles": [{"title": "My Explicit Dataset"}],
                "suffix": "test-doi-suffix-explicit"
            }
        }
        
        url = reverse('datacite-list')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["collection"], self.collection.id)
        
        datacite_obj = DataCite.objects.get(id=response.data["id"])
        self.assertEqual(datacite_obj.collection, self.collection)

    def test_rebuild_datacite_files_command(self):
        # Create a DataCite object initially without files or form_data alternateIdentifiers
        datacite_obj = DataCite.objects.create(
            user=self.user,
            curtain=self.main_curtain,
            collection=self.collection,
            title="Old Title",
            contact_email="test@example.com",
            pii_statement="None"
        )
        
        # Verify it has no local_file or alternate identifiers initially
        self.assertFalse(bool(datacite_obj.local_file))
        self.assertFalse(datacite_obj.form_data)
        
        # Call the management command to rebuild files for this DataCite object
        call_command('rebuild_datacite_files', datacite_obj.id)
        
        # Refresh from db and verify files and alternate identifiers have been rebuilt successfully
        datacite_obj.refresh_from_db()
        self.assertTrue(bool(datacite_obj.local_file))
        self.assertEqual(datacite_obj.local_file.read(), b"main session content")
        
        alternate_ids = datacite_obj.form_data["alternateIdentifiers"]
        alternate_id_types = [item["alternateIdentifierType"] for item in alternate_ids]
        
        self.assertIn("Curtain Main Session Data", alternate_id_types)
        self.assertIn("Curtain Alternative Session Data", alternate_id_types)
        self.assertIn("Curtain Collection Metadata", alternate_id_types)

    def test_rebuild_datacite_files_admin_action(self):
        # Instantiate model admin
        admin_instance = DataCiteAdmin(model=DataCite, admin_site=AdminSite())
        
        datacite_obj = DataCite.objects.create(
            user=self.user,
            curtain=self.main_curtain,
            collection=self.collection,
            title="Admin Old Title",
            contact_email="test@example.com",
            pii_statement="None"
        )
        
        mock_request = MagicMock()
        mock_request.build_absolute_uri.side_effect = lambda path: f"http://testserver{path}"
        mock_queryset = DataCite.objects.filter(id=datacite_obj.id)
        
        # Run action
        admin_instance.rebuild_datacite_files(mock_request, mock_queryset)
        
        # Verify
        datacite_obj.refresh_from_db()
        self.assertTrue(bool(datacite_obj.local_file))
        self.assertEqual(datacite_obj.local_file.read(), b"main session content")