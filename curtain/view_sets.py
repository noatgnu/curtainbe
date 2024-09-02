import base64
import json
import logging
import os
import uuid
from datetime import timedelta

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.core.files.base import File as djangoFile
from django.contrib.auth.models import User, AnonymousUser
from django.db.models import Q, Count, OuterRef, Subquery
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page, never_cache
# from django_sendfile import sendfile
from filters.mixins import FiltersMixin
from rest_flex_fields import is_expanded
from rest_flex_fields.views import FlexFieldsMixin
from rest_framework import viewsets, filters, permissions
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response
import pandas as pd
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework_simplejwt.tokens import AccessToken
from uniprotparser.betaparser import UniprotParser
import numpy as np
from rest_framework import status
from django.db import transaction
import io

from curtain.models import Curtain, CurtainAccessToken, KinaseLibraryModel, DataFilterList, UserPublicKey, UserAPIKey, \
    DataAESEncryptionFactors, LastAccess
from curtain.permissions import IsOwnerOrReadOnly, IsFileOwnerOrPublic, IsCurtainOwnerOrPublic, HasCurtainToken, \
    IsCurtainOwner, IsNonUserPostAllow, IsDataFilterListOwner, HasUserAPIKey
from curtain.serializers import UserSerializer, CurtainSerializer, KinaseLibrarySerializer, DataFilterListSerializer, \
    UserPublicKeySerializer, UserAPIKeySerializer
from curtain.utils import is_user_staff, delete_file_related_objects, calculate_boxplot_parameters, \
    check_nan_return_none, get_uniprot_data, encrypt_data
from curtain.validations import curtain_query_schema, kinase_library_query_schema, data_filter_list_query_schema
from curtainbe import settings


class UserViewSet(FlexFieldsMixin, FiltersMixin, viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if is_expanded(self.request, 'project'):
            self.queryset = self.queryset.prefetch_related('project')
        if is_expanded(self.request, 'curtain'):
            self.queryset = self.queryset.prefetch_related('curtain')

        return self.queryset


class DataFilterListViewSet(FiltersMixin, viewsets.ModelViewSet):
    queryset = DataFilterList.objects.all()
    serializer_class = DataFilterListSerializer
    filter_backends = [filters.OrderingFilter]
    permission_classes = [IsDataFilterListOwner | permissions.IsAuthenticatedOrReadOnly, ]
    parser_classes = [MultiPartParser, JSONParser]
    ordering_fields = ("id", "name", "category")
    ordering = ("name", "category", "id")
    filter_mappings = {
        "id": "id",
        "name_exact": "name__exact",
        "category_exact": "category__exact",
    }
    filter_validation_schema = data_filter_list_query_schema

    def get_queryset(self):
        name = self.request.query_params.get("name", None)
        data = self.request.query_params.get("data", None)
        category = self.request.query_params.get("category", None)
        query = Q()
        if name:
            query.add(Q(name__icontains=name), Q.OR)
        if data:
            query.add(Q(data__icontains=data), Q.OR)
        if category:
            query.add(Q(category__icontains=category), Q.OR)
        result = self.queryset.filter(query)
        if self.request.user:
            if self.request.user.is_authenticated:
                query = Q()
                query.add(Q(default=True), Q.OR)
                query.add(Q(user=self.request.user), Q.OR)
                return result.filter(query).distinct()
        return result.filter(default=True).distinct()

    def create(self, request, *args, **kwargs):
        filter_list = DataFilterList(
            name=self.request.data["name"],
            data=self.request.data["data"],
            category="User's lists",
            user=self.request.user
        )

        filter_list.save()
        filter_data = DataFilterListSerializer(filter_list, many=False, context={"request": request})
        return Response(data=filter_data.data)

    def destroy(self, request, *args, **kwargs):
        filter_list = self.get_object()
        filter_list.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["get"], detail=False, permission_classes=[permissions.AllowAny])
    def get_all_category(self, request, *args, **kwargs):
        categories = DataFilterList.objects.values("category").distinct()
        # results = [i["category"] for i in categories if i["category"] != ""]
        results = [i["category"] for i in categories if i["category"] != ""]
        return Response(data=results, )


class CurtainViewSet(FiltersMixin, viewsets.ModelViewSet):
    queryset = Curtain.objects.all()
    serializer_class = CurtainSerializer
    filter_backends = [filters.OrderingFilter]
    parser_classes = [MultiPartParser, JSONParser]
    permission_classes = [(permissions.IsAdminUser | IsNonUserPostAllow | IsCurtainOwnerOrPublic), ]
    lookup_field = 'link_id'
    ordering_fields = ("id", "created")
    ordering = ("created", "id")
    filter_mappings = {
        "id": "id",
        "username": "owners__username",
        "description": "description__icontains",
        "curtain_type": "curtain_type__in"
    }
    filter_validation_schema = curtain_query_schema

    def get_queryset(self):
        # Define a subquery to get the latest LastAccess for each Curtain
        latest_last_access_subquery = LastAccess.objects.filter(
            curtain=OuterRef('pk')
        ).order_by('-last_access').values('last_access')[:1]

        # Annotate the Curtain queryset with the latest last_access date
        self.queryset = self.queryset.annotate(
            latest_last_access=Subquery(latest_last_access_subquery)
        )

        # Get the date 90 days ago
        ninety_days_ago = timezone.now() - timedelta(days=90)

        # Filter the Curtain queryset based on the conditions
        query = Q(permanent=True) | Q(latest_last_access__isnull=True) | Q(latest_last_access__gte=ninety_days_ago)
        self.queryset = self.queryset.filter(query)

        return self.queryset

    def get_object(self):
        return super().get_object()

    @action(methods=["get"], url_path="download/?token=(?P<token>[^/]*)", detail=True, permission_classes=[
        permissions.IsAdminUser | HasCurtainToken | IsCurtainOwnerOrPublic
    ])
    @method_decorator(cache_page(0))
    def download(self, request, pk=None, link_id=None, token=None):

        c = self.get_object()
        # return sendfile(request, c.file.url)
        # headers = {
        #     'Location': c.file.url,
        #     "Access-Control-Allow-Origin": request.headers['Origin'],
        #     "Access-Control-Allow-Credentials": "true",
        #     "Vary": "Origin",
        # }
        # logging.info(c.file.url)
        LastAccess.objects.create(curtain=c)
        return Response(data={"url": c.file.url}, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True, permission_classes=[permissions.IsAdminUser | IsCurtainOwner])
    def generate_token(self, request, pk=None, link_id=None):
        c = self.get_object()
        a = AccessToken()
        a.set_exp(lifetime=timedelta(days=self.request.data["lifetime"]))
        ca = CurtainAccessToken(token=str(a), curtain=c)
        ca.save()

        return Response(data={"link_id": c.link_id, "token": ca.token})

    def encrypt_data(self, curtain):
        if "encrypted" in self.request.data:
            if self.request.data["encrypted"] == "True":
                curtain.encrypted = True
                if "e2e" in self.request.data:
                    if self.request.data["e2e"] == "True":
                        if "encryptedKey" in self.request.data and "encryptedIV" in self.request.data:
                            factors = DataAESEncryptionFactors(encrypted_iv=self.request.data["encryptedIV"],
                                                               encrypted_decryption_key=self.request.data[
                                                                   "encryptedKey"])
                            return factors
                    else:
                        return
                # if type(self.request.user) != AnonymousUser:
                #     public_key: UserPublicKey | None = UserPublicKey.objects.filter(user=self.request.user).first()
                #     if public_key:
                #         curtain.encrypted_with = public_key
                #         encrypted = encrypt_data(public_key.public_key, self.request.data["file"].read())
                #         curtain.file.save(str(curtain.link_id) + ".json",
                #                           djangoFile(io.BytesIO(encrypted), name=str(curtain.link_id) + ".json"))
                #else:
                #    raise ValueError("No public key found")
            else:
                curtain.encrypted = False

        else:
            return

    @action(methods=["get"], detail=True, permission_classes=[permissions.IsAdminUser | HasCurtainToken | IsCurtainOwnerOrPublic])
    def get_encryption_factors(self, request, **kwargs):
        c: Curtain = self.get_object()
        if c.encrypted:
            factors = c.encryption_factors.all()[0]
            return Response(data={"encryption_key": factors.encrypted_decryption_key, "encryption_iv": factors.encrypted_iv})
        return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["post"], detail=True, permission_classes=[permissions.IsAdminUser | HasCurtainToken | IsCurtainOwnerOrPublic])
    def set_encryption_factors(self, request, **kwargs):
        c: Curtain = self.get_object()
        if c.encrypted:
            factors = DataAESEncryptionFactors(encrypted_iv=request.data["encryption_iv"], encrypted_decryption_key=request.data["encryption_key"], curtain=c)
            factors.save()
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, **kwargs):
        c = Curtain()
        factors = self.encrypt_data(c)
        c.file.save(str(c.link_id) + ".json", djangoFile(self.request.data["file"]))
        if "description" in self.request.data:
            c.description = self.request.data["description"]

        if "enable" in self.request.data:
            if self.request.data["enable"] == "True":
                c.enable = True
            else:
                c.enable = False
        if "curtain_type" in self.request.data:
            c.curtain_type = self.request.data["curtain_type"]
        if "permanent" in self.request.data:
            if self.request.data["permanent"] == "True":
                c.permanent = True
            else:
                c.permanent = False
        c.save()
        if factors is not None:
            factors.curtain = c
            factors.save()
        if type(self.request.user) != AnonymousUser:
            c.owners.add(self.request.user)
        curtain_json = CurtainSerializer(c, many=False, context={"request": request})
        if type(self.request.user) != AnonymousUser:
            if settings.CURTAIN_DEFAULT_USER_LINK_LIMIT != 0:
                total_count = self.request.user.curtain.count()
                self.request.user.extraproperties.curtain_link_limit_exceed = total_count >= settings.CURTAIN_DEFAULT_USER_LINK_LIMIT
            else:
                self.request.user.extraproperties.curtain_link_limit_exceed = False
            self.request.user.extraproperties.save()

        print(curtain_json.data)
        return Response(data=curtain_json.data)

    @action(methods=["post"], detail=False, permission_classes=[permissions.IsAuthenticated])
    def create_encrypted(self, request, **kwargs):
        c = Curtain()
        c.file.save(str(c.link_id) + ".json", djangoFile(self.request.data["file"]))
        if "description" in self.request.data:
            c.description = self.request.data["description"]


        if "enable" in self.request.data:
            if self.request.data["enable"] == "True":
                c.enable = True
            else:
                c.enable = False
        if "curtain_type" in self.request.data:
            c.curtain_type = self.request.data["curtain_type"]
        c.encrypted = True
        c.save()
        curtain_json = CurtainSerializer(c, many=False, context={"request": request})
        if settings.CURTAIN_DEFAULT_USER_LINK_LIMIT != 0:
            total_count = self.request.user.curtain.count()
            self.request.user.extraproperties.curtain_link_limit_exceed = total_count >= settings.CURTAIN_DEFAULT_USER_LINK_LIMIT
        else:
            self.request.user.extraproperties.curtain_link_limit_exceed = False
        self.request.user.extraproperties.save()
        if type(self.request.user) != AnonymousUser:
            c.owners.add(self.request.user)
        return Response(data=curtain_json.data)

    @action(methods=["post"], detail=False, permission_classes=[HasAPIKey])
    def api_create(self, request, **kwargs):
        if "HTTP_AUTHORIZATION" in request.META:
            try:
                key = request.META["HTTP_AUTHORIZATION"].split()[1]
                api_key = UserAPIKey.objects.get_from_key(key)
                if not api_key.can_create:
                    return Response(status=status.HTTP_401_UNAUTHORIZED)
                user = api_key.user
                self.request.user = user
            except ValueError as e:
                return Response(status=status.HTTP_401_UNAUTHORIZED)

        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return self.create(request, **kwargs)

    @action(methods=["post"], detail=False, permission_classes=[HasAPIKey])
    def api_create_encrypted(self, request, **kwargs):
        if "HTTP_AUTHORIZATION" in request.META:
            try:
                key = request.META["HTTP_AUTHORIZATION"].split()[1]
                api_key = UserAPIKey.objects.get_from_key(key)
                if not api_key.can_create:
                    return Response(status=status.HTTP_401_UNAUTHORIZED)
                user = api_key.user
                self.request.user = user
            except ValueError as e:
                return Response(status=status.HTTP_401_UNAUTHORIZED)

        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return self.create_encrypted(request, **kwargs)

    @action(methods=["patch"], detail=True, permission_classes=[permissions.IsAdminUser | IsCurtainOwner])
    def api_update(self, request, **kwargs):
        if "HTTP_AUTHORIZATION" in request.META:
            try:
                key = request.META["HTTP_AUTHORIZATION"].split()[1]
                api_key = UserAPIKey.objects.get_from_key(key)
                user = api_key.user
                if not api_key.can_update:
                    return Response(status=status.HTTP_401_UNAUTHORIZED)
                self.request.user = user
            except ValueError as e:
                return Response(status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return self.update(request, **kwargs)

    def update(self, request, *args, **kwargs):
        c = self.get_object()
        factors = self.encrypt_data(c)

        if "enable" in self.request.data:
            if self.request.data["enable"] == "True":
                c.enable = True
            else:
                c.enable = False
        try:
            self.encrypt_data(c)
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if "file" in self.request.data:
            c.file.save(str(c.link_id) + ".json", djangoFile(self.request.data["file"]))
        if "description" in self.request.data:
            c.description = self.request.data["description"]

        c.save()
        if factors:
            factors.curtain = c
            factors.save()
        curtain_json = CurtainSerializer(c, many=False, context={"request": request})
        return Response(data=curtain_json.data)

    @action(methods=["get"], detail=True, permission_classes=[
        permissions.IsAdminUser | IsCurtainOwner
    ])
    def get_ownership(self, request, pk=None, link_id=None):
        c = self.get_object()
        if self.request.user in c.owners.all():
            return Response(data={"link_id": c.link_id, "ownership": True})
        return Response(data={"link_id": c.link_id, "ownership": False})

    @action(methods=["get"], detail=True, permission_classes=[
        permissions.IsAdminUser | HasCurtainToken | IsCurtainOwner
    ])
    def get_owners(self, request, pk=None, link_id=None):
        c = self.get_object()
        owners = []
        for i in c.owners.all():
            owners.append({"id": i.id, "username": i.username})
        return Response(data={"link_id": link_id, "owners": owners})

    @action(methods=["patch"], detail=True, permission_classes=[
        permissions.IsAdminUser | IsCurtainOwner
    ])
    def add_owner(self, request, pk=None, link_id=None):
        c = self.get_object()
        if "username" in self.request.data:
            user = User.objects.filter(username=self.request.data["username"]).first()
            if user:
                if user not in c.owners.all():
                    c.owners.add(user)
                    c.save()
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                user = User.objects.create_user(username=self.request.data["username"],
                                                password=User.objects.make_random_password())
                if user not in c.owners.all():
                    c.owners.add(user)
                    c.save()
                return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["get"], detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_curtain_list(self, request, pk=None, link_id=None):
        cs = self.request.user.curtain.all()
        cs_json = CurtainSerializer(cs, many=True, context={"request": request})
        return Response(data=cs_json.data)

    def destroy(self, request, *args, **kwargs):
        curtain = self.get_object()
        print("Deleting", curtain)
        curtain.delete()
        if settings.CURTAIN_DEFAULT_USER_LINK_LIMIT != 0:
            total_count = self.request.user.curtain.count()
            self.request.user.extraproperties.curtain_link_limit_exceed = total_count >= settings.CURTAIN_DEFAULT_USER_LINK_LIMIT
        else:
            self.request.user.extraproperties.curtain_link_limit_exceed = False
        self.request.user.extraproperties.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class KinaseLibraryViewSet(FiltersMixin, viewsets.ModelViewSet):
    queryset = KinaseLibraryModel.objects.all()
    serializer_class = KinaseLibrarySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, ]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ("id", "entry")
    ordering = ("entry")
    filter_mappings = {
        "id": "id",
        "position": "position",
        "entry": "entry",
        "residue": "residue"
    }
    filter_validation_schema = kinase_library_query_schema


def update_section(section, data_array, model):
    section.clear()
    for ct in data_array:
        if "id" in ct:
            if ct["id"]:
                cell_type = model.objects.get(pk=ct["id"])
                section.add(cell_type)
            else:
                if "name" in ct:
                    cell_type = model.objects.filter(name__exact=ct["name"]).first()
                    if cell_type:
                        section.add(cell_type)
                # cell_type = model(**ct)
                # cell_type.save()
                # section.add(cell_type)
        else:
            if "name" in ct:
                cell_type = model.objects.filter(name__exact=ct["name"]).first()
                if cell_type:
                    section.add(cell_type)
                else:
                    cell_type = model(**ct)
                    cell_type.save()
                    section.add(cell_type)
            # cell_type = model(**ct)
            # cell_type.save()
            # section.add(cell_type)


class UserPublicKeyViewSets(viewsets.ModelViewSet):
    queryset = UserPublicKey.objects.all()
    serializer_class = UserPublicKeySerializer
    permission_classes = [permissions.IsAuthenticated, ]
    parser_classes = [MultiPartParser, JSONParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ("id", "created")
    ordering = ("created", "id")

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        user_public_key = UserPublicKey(user=self.request.user, public_key=self.request.data["public_key"])
        user_public_key.save()
        return Response(status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        user_public_key = self.get_object()
        user_public_key.public_key = self.request.data["public_key"]
        user_public_key.save()
        return Response(status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        user_public_key = self.get_object()
        user_public_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserAPIKeyViewSets(viewsets.ModelViewSet):
    queryset = UserAPIKey.objects.all()
    serializer_class = UserAPIKeySerializer
    permission_classes = [permissions.IsAuthenticated, ]
    lookup_field = "id"
    lookup_value_regex = '[^/]+'

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def get_object(self):
        queryset = self.get_queryset()
        print(self.kwargs)
        filter_id = self.kwargs[self.lookup_field]
        print(filter_id)
        data_object = queryset.get(id=filter_id)
        self.check_object_permissions(self.request, data_object)
        return data_object

    def create(self, request, *args, **kwargs):
        api_key, key = UserAPIKey.objects.create_key(name=self.request.data["name"], user=self.request.user)
        return Response(data={"key": key}, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        api_key = self.get_object()
        if api_key.user != self.request.user:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        api_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)