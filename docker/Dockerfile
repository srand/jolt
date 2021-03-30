FROM python:3-slim

RUN pip3 install virtualenv

COPY . /opt/jolt
RUN pip3 install -e /opt/jolt[allure,amqp]
ENTRYPOINT ["jolt"]
CMD []

RUN mkdir /ws
WORKDIR /ws
