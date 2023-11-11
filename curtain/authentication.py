from django.contrib.auth.models import User
from rest_framework import authentication
from rest_framework import exceptions


class APIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.META.get('HTTP_X_API_KEY')
        if not api_key:
            raise exceptions.AuthenticationFailed('No API key provided.')
        try:
            user = User.objects.get(api_key=api_key)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key.')
        return (user, None)