import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from rooms.routing import websocket_urlpatterns  # noqa: E402

_ws = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
if not settings.DEBUG:
    _ws = AllowedHostsOriginValidator(_ws)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": _ws,
    }
)
