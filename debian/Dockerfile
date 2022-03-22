FROM debian:latest as tools
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update
RUN apt-get install -y dpkg-dev
RUN apt-get install -y debhelper dh-python python3-all python3-bz2file python3-click python3-colorama python3-fasteners python3-jinja2 python3-keyring python3-keyrings.alt python3-lxml python3-multi-key-dict python3-pygit2 python3-requests python3-setuptools python3-tqdm

FROM tools as build
COPY . /usr/src
WORKDIR /usr/src
RUN cd jolt* && dpkg-buildpackage

FROM scratch
COPY --from=build /usr/src/*.deb /