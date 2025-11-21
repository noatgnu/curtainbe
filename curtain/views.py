import json
import re
from datetime import datetime, timedelta

import django_rq

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncWeek
from django.http import FileResponse, Http404
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.response import Response
from rq.job import Job
from scipy.stats import ttest_ind

from curtain.models import User, ExtraProperties, SocialPlatform, Curtain, UserAPIKey, DataCite
from curtainbe import settings
import requests
from request.models import Request
from curtain.worker_tasks import compare_session
import kinase_library as kl

class LogoutView(APIView):
    """
    View to handle user logout by blacklisting the refresh token.
    """
    permission_classes = (IsAuthenticated,)
    # only access this view if user is authenticated

    def post(self, request):
        # try to blacklist the refresh token and return 205 if successful or 400 if not successful (bad request)
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            print(e)
            return Response(status=status.HTTP_400_BAD_REQUEST)

# View to get user information
class UserView(APIView):
    """
    View to get information about the currently authenticated user.
    """
    permission_classes = (IsAuthenticated,)
    # only access this view if user is authenticated

    def post(self, request, *args, **kwargs):
        # get user information and return it as json
        # if user is staff, return is_staff = true
        if 'HTTP_AUTHORIZATION' in request.META:
            authorization = request.META['HTTP_AUTHORIZATION'].replace("Bearer ", "")
            # get user from access token
            access_token = AccessToken(authorization)
            user = User.objects.filter(pk=access_token["user_id"]).first()
            extra = ExtraProperties.objects.filter(user=user).first()
            # create extra properties if they don't exist
            if not extra:
                extra = ExtraProperties(user=user)
                extra.save()
            # create user json
            user_json = {
                    "username": user.username,
                    "id": user.id,
                    "total_curtain": user.curtain.count()
                }
            if user.is_staff:
                user_json["is_staff"] = True
            else:
                user_json["is_staff"] = False
            if settings.CURTAIN_ALLOW_NON_STAFF_DELETE:
                user_json["can_delete"] = True
            else:
                user_json["can_delete"] = user_json["is_staff"]
            user_json["curtain_link_limit"] = user.extraproperties.curtain_link_limits
            user_json["curtain_link_limit_exceed"] = user.extraproperties.curtain_link_limit_exceed
            # return user json
            if user:
                return Response(user_json)
        # if user is not authenticated, return 404
        return Response(status=status.HTTP_404_NOT_FOUND)

# View for handling ORCID OAuth
class ORCIDOAUTHView(APIView):
    """
    View to handle the OAuth2 flow for ORCID authentication.
    It exchanges an authorization code for an access token and creates or logs in a user.
    """
    permission_classes = (AllowAny,)
    # user can post to this view without being authenticated
    # this view will handle the OAuth process

    def post(self, request):
        print(self.request.data)
        # check if the request contains the auth_token and redirect_uri
        if "auth_token" in self.request.data and "redirect_uri" in self.request.data:
            payload = {
                "client_id": settings.ORCID["client_id"],
                "client_secret": settings.ORCID["secret"],
                "grant_type": "authorization_code",
                "code": self.request.data["auth_token"],
                "redirect_uri": self.request.data["redirect_uri"]
            }
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            # post the request to the ORCID API to get the user data
            response = requests.post("https://orcid.org/oauth/token", payload, headers=headers)
            data = json.loads(response.content.decode())
            # check if the user has already been created from the ORCID ID
            try:
                # get the user from the ORCID ID
                user = User.objects.filter(username=data["orcid"]).first()

                # print(user)
                # check if the user exists
                if user:
                    # check if the user has been assigned a social platform
                    social = SocialPlatform.objects.filter(name="ORCID").first()
                    if social:
                        if social is not user.extraproperties.social_platform:
                            # assign the user to the social platform
                            user.extraproperties.social_platform = social
                            user.extraproperties.save()
                    # create a refresh token for the user
                    remember_me = self.request.data.get("remember_me", False)
                    refresh_token = RefreshToken.for_user(user)

                    if remember_me:
                        refresh_token.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_REFRESH_TOKEN_LIFETIME_DAYS))
                        access_token = refresh_token.access_token
                        access_token.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_ACCESS_TOKEN_LIFETIME_DAYS))
                    else:
                        access_token = refresh_token.access_token

                    return Response(data={"refresh": str(refresh_token), "access": str(access_token)})
                else:
                    # create a new user with the ORCID ID as the username
                    user = User.objects.create_user(username=data["orcid"],
                                                    password=User.objects.make_random_password())
                    #user.is_authenticated = True

                    #user.save()
                    # create a new ExtraProperties object for the user
                    ex = ExtraProperties(user=user)
                    ex.save()
                    # assign the user to the ORCID social platform
                    social = SocialPlatform.objects.get_or_create(SocialPlatform(name="ORCID"))
                    social.save()
                    ex.social_platform = social
                    ex.save()
                    # create a refresh token for the user
                    remember_me = self.request.data.get("remember_me", False)
                    refresh_token = RefreshToken.for_user(user)

                    if remember_me:
                        refresh_token.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_REFRESH_TOKEN_LIFETIME_DAYS))
                        access_token = refresh_token.access_token
                        access_token.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_ACCESS_TOKEN_LIFETIME_DAYS))
                    else:
                        access_token = refresh_token.access_token

                    return Response(data={"refresh": str(refresh_token), "access": str(access_token)})
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer to handle 'remember_me' parameter.
    """
    remember_me = serializers.BooleanField(default=False, required=False, write_only=True)

    def validate(self, attrs):
        remember_me = attrs.pop('remember_me', False)
        data = super().validate(attrs)

        if remember_me:
            refresh = RefreshToken.for_user(self.user)
            refresh.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_REFRESH_TOKEN_LIFETIME_DAYS))
            access = refresh.access_token
            access.set_exp(lifetime=timedelta(days=settings.JWT_REMEMBER_ME_ACCESS_TOKEN_LIFETIME_DAYS))
            data['refresh'] = str(refresh)
            data['access'] = str(access)

        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token view that supports 'remember_me' parameter.
    """
    serializer_class = CustomTokenObtainPairSerializer


# Get general site properties
class SitePropertiesView(APIView):
    """
    View to return general site-wide settings and properties.
    """
    permission_classes = (AllowAny,)

    def get(self, request, format=None):
        return Response(data={
            "non_user_post": settings.CURTAIN_ALLOW_NON_USER_POST,
            "allow_user_set_permanent": settings.CURTAIN_ALLOW_USER_SET_PERMANENT,
            "expiry_duration_options": [3, 6],
            "default_expiry_duration_months": 3,
            "jwt_access_token_lifetime_minutes": settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES,
            "jwt_refresh_token_lifetime_days": settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS,
            "jwt_remember_me_access_token_lifetime_days": settings.JWT_REMEMBER_ME_ACCESS_TOKEN_LIFETIME_DAYS,
            "jwt_remember_me_refresh_token_lifetime_days": settings.JWT_REMEMBER_ME_REFRESH_TOKEN_LIFETIME_DAYS
        })

# Kinase Library Proxy view for getting kinase scores
class KinaseLibraryProxyView(APIView):
    """
    A proxy view to the external Kinase Library API for scoring sequences.
    """
    permission_classes = (AllowAny,)
    # user can get this view without being authenticated

    def get(self, request, format=None):
        # check if the request contains the sequence
        if request.query_params['sequence']:
            # index of s/t/y in the sequence case sensitive
            letters = ['s', 't', 'y']
            if not any(letter in request.query_params['sequence'].lower() for letter in letters):
                return Response(status=status.HTTP_400_BAD_REQUEST)
            for letter in letters:
                pos = str.find(request.query_params['sequence'], letter)
                if pos != -1:
                    s = kl.Substrate(request.query_params['sequence'], phos_pos=pos+1)
                    #res = requests.get(f"https://kinase-library.phosphosite.org/api/scorer/score-site/{request.query_params['sequence']}/")
                    res = s.predict()
                    res = res.reset_index()
                    data = res.to_dict("records")
                    return Response(data=data)
        # if the request does not contain the sequence, return a 400 error
        return Response(status=status.HTTP_400_BAD_REQUEST)

# View for getting Curtain download stats
class DownloadStatsView(APIView):
    """
    View to get the total number of Curtain downloads.
    """
    permission_classes = (AllowAny,)
    # user can get this view without being authenticated

    def get(self, request, format=None):
        # get the number of downloads
        # this is done by filtering the django_request table for requests that match the download url
        download_stats = Request.objects.filter(path__regex="\/curtain\/[a-z0-9\-]+\/download\/\w*").count()
        return Response(data={
            "download": download_stats
        })

class StatsView(APIView):
    """
    View to get more detailed statistics about Curtain usage,
    including downloads and creations per day and per week.
    """
    permission_classes = (AllowAny,)

    def get(self, request, last_n_days, format=None):
        # get the number of downloads request per day
        # this is done by filtering the django_request table for requests that match the download url and truncate the time field to date

        download_stats = Request.objects.filter(path__regex="\/curtain\/[a-z0-9\-]+\/download\/\w*", time__gte=datetime.now()-timedelta(days=last_n_days))
        download_per_day = (download_stats.annotate(date=TruncDay('time')).values('date').annotate(downloads=Count("response")))
        result = []
        for i in download_per_day:
            result.append({"date": i["date"].strftime("%Y-%m-%d"), "downloads": i["downloads"]})
        curtain_stats = Curtain.objects.filter(created__gte=datetime.now()-timedelta(days=last_n_days))
        created_per_day = (curtain_stats.annotate(date=TruncDay('created')).values('date').annotate(count=Count("id")))
        result2 = []
        for i in created_per_day:
            result2.append({"date": i["date"].strftime("%Y-%m-%d"), "count": i["count"]})
        download_per_week = (download_stats.annotate(date=TruncWeek('time')).values('date').annotate(downloads=Count("response")))
        result3 = []
        for i in download_per_week:
            result3.append({"date": i["date"].strftime("%Y-%m-%d"), "downloads": i["downloads"]})
        created_per_week = (curtain_stats.annotate(date=TruncWeek('created')).values('date').annotate(count=Count("id")))
        result4 = []
        for i in created_per_week:
            result4.append({"date": i["date"].strftime("%Y-%m-%d"), "count": i["count"]})

        return Response(data={
            "session_download_per_day": result,
            "session_created_per_day": result2,
            "session_download_per_week": result3,
            "session_created_per_week": result4
        })

class InteractomeAtlasProxyView(APIView):
    """
    A proxy view to the Interactome Atlas API.
    """
    permission_classes = (AllowAny,)

    def post(self, request, format=None):
        if request.data["link"]:
            res = requests.get(request.data["link"].replace("https", "http"))
            return Response(data=res.json())
        return Response(status=status.HTTP_400_BAD_REQUEST)

class PrimitiveStatsTestView(APIView):
    """
    A view to perform a primitive statistical t-test on provided data.
    """
    permission_classes = (AllowAny,)

    def post(self, request, format=None):
        test_type = request.data["type"]
        test_data = request.data["data"]
        if test_type == "t-test":
            x = ttest_ind(test_data[0], test_data[1])
            return Response(data={
                "test_statistic": x.statistic, "p_value": x.pvalue, "degrees_of_freedom": x.df
            })
        print(test_type, test_data)
        return Response(status=status.HTTP_400_BAD_REQUEST)

class CompareSessionView(APIView):
    """
    A view to initiate a background job to compare data from multiple Curtain sessions.
    It uses Django Channels to send real-time feedback to the client.
    """
    permission_classes = (AllowAny,)

    def post(self, request, format=None):
        id_list = request.data["idList"]
        study_list = request.data["studyList"]
        match_type = request.data["matchType"]
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(request.data["sessionId"], {
            'type': 'job_message',
            'message': {
                'message': "Started operation",
                'senderName': "Server",
                'requestType': "Compare Session",
                'operationId': ""
            }
        })
        to_be_processed_list = []
        curtain_list = Curtain.objects.filter(link_id__in=id_list)
        for item in curtain_list:
            owners = item.owners.all()
            if len(owners) > 0:
                if not item.enable:
                    if request.user and request.user.is_authenticated and request.user in owners and request.user:
                        to_be_processed_list.append(item.link_id)
                else:
                    to_be_processed_list.append(item.link_id)
            else:
                to_be_processed_list.append(item.link_id)
        job = compare_session.delay(to_be_processed_list, study_list, match_type, request.data["sessionId"])
        return Response(data={"job_id": job.id})


class JobResultView(APIView):
    """
    A view to check the status and result of a background job.
    """
    permission_classes = (AllowAny,)
    def get(self, request, job_id):
        connection = django_rq.get_connection()
        task = Job.fetch(job_id, connection=connection)

        if task:
            job_status = task.get_status()
            if job_status == 'finished':
                return Response(data=task.result)
            elif job_status == 'failed':
                return Response(data={"status": "failed"})
            elif job_status == 'started':
                return Response(data={"status": "progressing"})
            elif job_status == 'queued':
                return Response(data={"status": "queued"})
            else:
                return Response(data={"status": "unknown"})
        else:
            return Response(status=status.HTTP_404_NOT_FOUND)

class APIKeyView(APIView):
    """
    A simpler, non-ViewSet view for managing user API keys.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        key_name = self.request.data["name"]
        user_api_key, key = UserAPIKey.objects.create_key(name=key_name, user=self.request.user)
        return Response(data={"key": key})

    def delete(self, request):
        key_name = self.request.data["name"]
        keys = self.request.user.api_keys.all()
        keys.filter(name=key_name).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get(self, request):
        keys = self.request.user.api_keys.all()
        return Response(data={"keys": [{"name": key.name} for key in keys]})


class DataCiteFileView(APIView):
    """
    Public view for serving DataCite local files without authentication.
    """
    permission_classes = [AllowAny]

    def get(self, request, datacite_id):
        try:
            datacite = DataCite.objects.get(id=datacite_id)
            if not datacite.local_file:
                raise Http404("File not found")

            response = FileResponse(datacite.local_file.open('rb'))
            response['Content-Disposition'] = f'inline; filename="{datacite.local_file.name.split("/")[-1]}"'
            return response
        except DataCite.DoesNotExist:
            raise Http404("DataCite not found")

