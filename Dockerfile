FROM microservice_python3_focal
MAINTAINER Cerebro <cerebro@ganymede.eu>

RUN apt-get update && apt-get install -y libffi-dev libssl-dev
RUN pip install -U paramiko raven jinja2 armada==1.8

ADD ./supervisor/* /etc/supervisor/conf.d/
ADD . /opt/magellan

EXPOSE 80
