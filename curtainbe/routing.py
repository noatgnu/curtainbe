from django.urls import re_path

from curtainbe.consumers import CurtainConsumer, JobConsumer

websocket_urlpatterns = [
    re_path(r'ws/curtain/(?P<session_id>\w+)/(?P<personal_id>\w+)/$', CurtainConsumer.as_asgi()),
    re_path(r'ws/job/(?P<session_id>\w+)/(?P<personal_id>\w+)/$', JobConsumer.as_asgi()),
]
