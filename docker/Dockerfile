FROM python:3-buster
RUN apt-get update && apt-get install -y gcc make libffi-dev musl-dev libssl-dev git python3-pygit2
COPY . /opt/jolt
RUN pip3 install -e /opt/jolt
