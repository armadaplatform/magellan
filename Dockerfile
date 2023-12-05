FROM microservice_python3_focal
MAINTAINER Cerebro <cerebro@ganymede.eu>

RUN apt-get update && apt-get install -y libffi-dev libssl-dev
RUN pip install -U paramiko raven jinja2 armada boto3

ADD ./supervisor/* /etc/supervisor/conf.d/
ADD . /opt/magellan

EXPOSE 80
