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
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from curtain.view_sets import UserViewSet, KinaseLibraryViewSet, DataFilterListViewSet, CurtainViewSet, \
    UserAPIKeyViewSets, UserPublicKeyViewSets
from curtain.views import LogoutView, UserView, SitePropertiesView, ORCIDOAUTHView, KinaseLibraryProxyView, \
    DownloadStatsView, InteractomeAtlasProxyView, PrimitiveStatsTestView, CompareSessionView, StatsView, JobResultView

#from curtain.contrib import admin
#from curtain.urls import path
router = routers.DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'kinase_library', KinaseLibraryViewSet)
router.register(r'data_filter_list', DataFilterListViewSet)
router.register(r'curtain', CurtainViewSet)
#router.register(r'userapikey', UserAPIKeyViewSets)
#router.register(r'userpublickey', UserPublicKeyViewSets)

urlpatterns = [
    path('', include(router.urls)),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
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
    #path('admin/', admin.site.urls),
]
