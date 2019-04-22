FROM python:3.7-alpine
RUN apk update && apk add gcc make libffi-dev musl-dev openssl-dev git
COPY . /opt/jolt
RUN pip3 install -e /opt/jolt
