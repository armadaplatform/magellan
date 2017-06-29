FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

ENV CONFIG_DIR ./config

RUN apt-get update && apt-get install -y libffi-dev libssl-dev
RUN pip install -U paramiko raven jinja2

ADD ./supervisor/* /etc/supervisor/conf.d/
ADD . /opt/magellan

EXPOSE 80
