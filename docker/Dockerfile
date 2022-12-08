FROM python:3-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update
RUN apt-get install -y --no-install-recommends git ninja-build uidmap
RUN apt-get clean
RUN pip3 install virtualenv

COPY . /opt/jolt
RUN pip3 install -e /opt/jolt[allure,amqp]
ENTRYPOINT ["jolt"]
CMD []

RUN mkdir /ws
WORKDIR /ws
