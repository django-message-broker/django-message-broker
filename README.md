# Django Message Broker

<img src="assets/django_message_broker_icon_512.svg"
     alt="Django message broker icon"
     width="120"
     align="left"/>

A message broker connects processes both on the same host or on different hosts
to allow them to exchange information. Brokers can provide a wide range of services
though typically they receive, store and forward messages between different systems.

Django Message Broker is installed on the same host as Django web server and written
in Python. It is targetted at low volume solutions where it is not effective or
practical to deploy external servers such as Redis and RabbitMQ. Potential scenarios
for Django Message Broker include:

+ Prototyping, Testing, Training
+ Data science projects where complexity exceeds the capabilities of Shiny, Dash, Streamlit
+ Replacement for Microsoft Excel business forecasting models.
+ Small business systems with a low number of users.

The Django Message Broker does not replace the higher volume message brokers, and is
intended to provide an easy to install, all-in-one alternative for small scale solutions.

## Supported interfaces

<img src="assets/DMB Ecosystem opt.svg"
     alt="Django message broker ecosystem"
     width=320
     align="right"/>

Provide a little more

text about the interfaces

why and how

what they do

etc.

+ Django channels - An alternative to in-memory and Redis backends.
+ Celery - An alternative to RabbitMQ.
+ Process Workers - Non celery background workers.

## Installation

Install latest stable version into your python environment using pip::

    pip install django-message-broker

Once installed add ``django_message_broker`` to your ``INSTALLED_APPS`` in settings.py:

    INSTALLED_APPS = (
        'django_message_broker',
        ...        
    )

Django Message Broker should be installed as early as possible in the installed applications
list and ideally before other applications such as Channels and Celery. The message broker
forks a background process which should occur before other applications create new threads in
the current process.

## Configure Django Channels Layers

To configure the Django Message Broker as a Channels layer add the following to the ``CHANNEL_LAYERS``
setting in settings.py:

    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'django_channels_server.ChannelsServerLayer',
        },
    }
