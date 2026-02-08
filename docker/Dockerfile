FROM docker.io/python:3.14-slim
ENV DEBIAN_FRONTEND=noninteractive

COPY . /opt/jolt
RUN rm -rf /opt/jolt/jolt.egg-info /opt/jolt/requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install --upgrade -e /opt/jolt[allure]
ENTRYPOINT ["jolt"]
CMD []

RUN mkdir /ws
WORKDIR /ws
