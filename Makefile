VER ?= 1
REGISTRY = joltreg.azurecr.io

.DEFAULT: deploy
.PHONY: deploy

pypi-deploy:
	python3 -m pip install --user --upgrade setuptools wheel
	python3 setup.py sdist bdist_wheel
	python3 -m pip install --user --upgrade twine
	twine upload dist/*

.PHONY: docker
docker:
	docker build . -f docker/Dockerfile -t jolt:latest
	docker build . -f docker/Dockerfile.rabbitmq -t jolt:latest-rabbitmq
	docker tag jolt:latest-rabbitmq jolt:v${VER}-rabbitmq

kube-deploy: docker
	docker tag jolt:v${VER}-rabbitmq ${REGISTRY}/jolt:v${VER}-rabbitmq
	docker push ${REGISTRY}/jolt:v${VER}-rabbitmq
	kubectl rolling-update jolt-controller --image=${REGISTRY}/jolt:v${VER}-rabbitmq
