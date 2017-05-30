FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

ENV CONFIG_DIR ./config
RUN apt-get update -y && apt-get install -y libffi-dev libssl-dev
RUN pip install -U paramiko armada raven

ADD . /opt/magellan
ADD ./supervisor/* /etc/supervisor/conf.d/

EXPOSE 80
