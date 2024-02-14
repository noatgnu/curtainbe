from django.contrib.auth.models import User
from rest_framework import authentication
from rest_framework import exceptions

from curtain.models import UserAPIKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        key = request.META.get('HTTP_X_API_KEY')
        if not key:
            raise exceptions.AuthenticationFailed('No API key provided.')
        try:
            api_key = UserAPIKey.objects.get_from_key(key)
            user = api_key.user
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key.')
        return (user, None)
