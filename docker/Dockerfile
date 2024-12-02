FROM docker.io/python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libxml2-dev \
    libxslt-dev \
    ninja-build \
    python3-dev \
    python3-pygit2 \
    python3-virtualenv \
    uidmap

RUN apt-get clean

COPY . /opt/jolt
RUN pip3 install -e /opt/jolt[allure]
ENTRYPOINT ["jolt"]
CMD []

RUN mkdir /ws
WORKDIR /ws
