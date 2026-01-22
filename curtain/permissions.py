from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework_api_key.permissions import BaseHasAPIKey
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from curtain.models import CurtainAccessToken, UserAPIKey
from curtainbe import settings


class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user in obj.owners.all())

class IsFileOwnerOrPublic(BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.project.enable:
            return True
        return bool(request.user and request.user.is_authenticated and request.user in obj.project.owners.all())

class IsNonUserPostAllow(BasePermission):
    def has_permission(self, request, view):
        if settings.CURTAIN_ALLOW_NON_USER_POST:
            if request.method == "POST" or request.method == "PUT":
                return True
        return False
class IsCurtainOwnerOrPublic(BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.enable:
            if request.method in SAFE_METHODS:
                return True

        # if obj.project:
        #     if obj.project.enable:
        #         if request.method in SAFE_METHODS:
        #             return True
        #
        #     if bool(request.user and request.user.is_authenticated and not request.user.extraproperties.curtain_link_limit_exceed and request.user.extraproperties.curtain_post):
        #         return bool(request.user in obj.project.owners.all())
        # else:
        if bool(request.user and request.user.is_authenticated and not request.user.extraproperties.curtain_link_limit_exceed and request.user.extraproperties.curtain_post):
            return bool(request.user in obj.owners.all())

        return False


class HasCurtainToken(BasePermission):
    def has_object_permission(self, request, view, obj):
        token = view.kwargs.get("token", "")
        if token != "":
            t = CurtainAccessToken.objects.filter(token=token).first()
            if t:
                if t.curtain.link_id == view.kwargs.get("link_id", ""):
                    try:
                        access_token = AccessToken(token)
                        access_token.check_exp()
                        return True
                    except TokenError:
                        return False
        return False


class IsCurtainOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        if bool(request.user and request.user.is_authenticated):
            return bool(request.user in obj.owners.all())
        return False


class IsDataFilterListOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        if bool(request.user and request.user.is_authenticated):
            return bool(request.user == obj.user)


class IsCollectionOwner(BasePermission):
    """
    Permission to check if the user is the owner of the collection.
    """
    def has_object_permission(self, request, view, obj):
        if bool(request.user and request.user.is_authenticated):
            return bool(request.user == obj.owner)
        return False

class HasUserAPIKey(BaseHasAPIKey):
    model = UserAPIKey

    def has_permission(self, request, view):
        assert self.model is not None
        key = self.get_key(request)
        if key is None:
            return False
        return self.model.objects.is_valid(key)

    def has_object_permission(self, request, view, obj):
        assert self.model is not None
        key = self.get_key(request)
        if key is None:
            return False
        api_key = self.model.objects.get_from_key(key)
        user = api_key.user
        # check if object is DataFilterList
        if hasattr(obj, "user"):
            return bool(user == obj.user)
        # check if object is Curtain
        if hasattr(obj, "owners"):
            return bool(user in obj.owners.all())
        return False
