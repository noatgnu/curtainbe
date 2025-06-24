from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError
from curtain.models import ExtraProperties, SocialPlatform, UserPublicKey
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