from .slack_bot import router as slack_router
from .teams_bot import router as teams_router
from .whatsapp_bot import router as whatsapp_router
from .extension_api import router as extension_router
from .web_app import router as web_app_router

__all__ = ["slack_router", "teams_router", "whatsapp_router", "extension_router", "web_app_router"]
