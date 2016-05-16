FROM microservice_python
MAINTAINER Cerebro <cerebro@ganymede.eu>

RUN apt-get update -y && apt-get install -y libffi-dev libssl-dev
RUN pip install -U paramiko armada

ADD . /opt/magellan
ADD ./supervisor/* /etc/supervisor/conf.d/

EXPOSE 80
