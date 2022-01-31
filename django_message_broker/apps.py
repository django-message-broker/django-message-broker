import os

from multiprocessing import Process

from django.apps import AppConfig

from .server.channels_server import ChannelsServer


def run_message_broker_server():
    channels_database_process = ChannelsServer(ip_address="127.0.0.1", port=5556)
    channels_database_process.start()


class BackgroundTask(AppConfig):
    name = "django_message_broker"
    verbose_name = "Django message broker"

    def ready(self):
        if os.environ.get("RUN_MAIN", None) != "true":
            background_process = Process(name="msgbroker", target=run_message_broker_server)
            background_process.daemon = True
            background_process.start()
