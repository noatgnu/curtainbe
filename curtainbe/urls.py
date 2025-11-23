"""
URL configuration for curtainbe project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from curtain.view_sets import UserViewSet, KinaseLibraryViewSet, DataFilterListViewSet, CurtainViewSet, \
    UserAPIKeyViewSets, UserPublicKeyViewSets, DataCiteViewSets, AnnouncementViewSet, PermanentLinkRequestViewSet, \
    CurtainCollectionViewSet
from curtain.views import LogoutView, UserView, SitePropertiesView, ORCIDOAUTHView, KinaseLibraryProxyView, \
    DownloadStatsView, InteractomeAtlasProxyView, PrimitiveStatsTestView, CompareSessionView, StatsView, JobResultView, \
    APIKeyView, DataCiteFileView, CustomTokenObtainPairView
from curtain.chunked_upload import CurtainChunkedUploadView
from django.contrib import admin

router = routers.DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'kinase_library', KinaseLibraryViewSet)
router.register(r'data_filter_list', DataFilterListViewSet)
router.register(r'curtain', CurtainViewSet)
router.register(r'api_key', UserAPIKeyViewSets)
router.register(r'datacite', DataCiteViewSets)
router.register(r'announcements', AnnouncementViewSet)
router.register(r'permanent-link-requests', PermanentLinkRequestViewSet)
router.register(r'curtain-collections', CurtainCollectionViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('user/', UserView.as_view(), name="user"),
    path('site-properties/', SitePropertiesView.as_view(), name="site_properties"),
    path('rest-auth/orcid/', ORCIDOAUTHView.as_view(), name='orcid_login'),
    path('kinase_library_proxy/', KinaseLibraryProxyView.as_view(), name='kinase_library_proxy'),
    path('stats/download/', DownloadStatsView.as_view(), name='download_stats'),
    path('interactome-atlas-proxy/', InteractomeAtlasProxyView.as_view(), name='interactome_atlas_proxy'),
    path('primitive-stats-test/', PrimitiveStatsTestView.as_view(), name='primitive_stats_test'),
    path('compare-session/', CompareSessionView.as_view(), name='compare_session'),
    path('stats/summary/<int:last_n_days>/', StatsView.as_view(), name="stats_summary"),
    path(r'job/<str:job_id>/', JobResultView.as_view(), name='job_result'),
    path('datacite/file/<int:datacite_id>/', DataCiteFileView.as_view(), name='datacite_file'),
    path('curtain-chunked-upload/', CurtainChunkedUploadView.as_view(), name='curtain_chunked_upload'),
    path('curtain-chunked-upload/<uuid:pk>/', CurtainChunkedUploadView.as_view(), name='curtain_chunked_upload_detail'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
