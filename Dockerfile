FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

RUN pip install -U paramiko

ADD . /opt/magellan
ADD ./supervisor/magellan.conf /etc/supervisor/conf.d/

EXPOSE 80
