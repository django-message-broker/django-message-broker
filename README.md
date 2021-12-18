# Django Message Broker

Django Message Broker is a message broker written in Python which may be installed
with Django to provide cross process messaging functionality for commonly used
Django packages. The Django Message Broker is intended for low volume messaging where
external servers are impracticable.

The Django Message Broker supports:

+ Django channels - An alternative to in-memory and Redis backends.
+ Process Workers - Non celery background workers. 
+ Celery - An alternative to RabbitMQ
