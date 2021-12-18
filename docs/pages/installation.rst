Installation and configuration
==============================

Installing Django Message Broker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install latest stable version into your python environment using pip::

    pip install django-message-broker

Once installed add ``django_message_broker`` to your ``INSTALLED_APPS`` in settings.py::

    INSTALLED_APPS = (
        'django_message_broker',
        ...        
    )

Django Message Broker should be installed as early as possible in the installed applications
list and ideally before other applications such as Channels and Celery. The message broker
forks a background process which should occur before other applications create new threads in
the current process.

Configure Django Channels Layers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To configure the Django Message Broker as a Channels layer add the following to the ``CHANNEL_LAYERS``
setting in settings.py:

.. highlight:: python
.. code-block:: python

    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'django_channels_server.ChannelsServerLayer',
        },
    }
