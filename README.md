<img src="assets/django_message_broker_icon_512.svg"
     alt="Django message broker icon"
     height=120
     width=120
     style="margin-right:0; margin-left: auto; display:block;" />
# Django Message Broker

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

## The Django Message Broker supports

<img src="assets/DMB Ecosystem opt.svg"
     alt="Django message broker ecosystem"
     height=240
     width=320
     style="float: right; margin-left: 10px" />

+ Django channels - An alternative to in-memory and Redis backends.
+ Celery - An alternative to RabbitMQ.
+ Process Workers - Non celery background workers. 
