"""Django plug-in providing a localhost message broker implementation with
interfaces for Django Channels and Celery."""
from .layer import ChannelsServerLayer
from .process_client import ProcessClient

__version__ = "0.1.0"

__all__ = [
    "ChannelsServerLayer",
    "ProcessClient",
]
