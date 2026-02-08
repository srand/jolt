FROM docker.io/python:3.14-slim
ENV DEBIAN_FRONTEND=noninteractive

COPY . /opt/jolt
RUN pip3 install --upgrade -e /opt/jolt[allure]
ENTRYPOINT ["jolt"]
CMD []

RUN mkdir /ws
WORKDIR /ws
