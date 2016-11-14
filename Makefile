REGISTRY = my.registry.com
REGISTRY_PATH = my-org
IMAGE_NAME = janitor
IMAGE_VERSION ?= latest
IMAGE_PATH = ${REGISTRY}/${REGISTRY_PATH}/${IMAGE_NAME}:${IMAGE_VERSION}

build:
	docker build -t ${IMAGE_PATH} .

start: stop
	docker run -d --name $(IMAGE_NAME) \
		-e ETCD_HOST=127.0.0.1 \
		-e TZ=Europe/Moscow \
		-e CRON_MINUTE=* \
		-v /var/run/docker.sock:/var/run/docker.sock \
		${IMAGE_PATH}

stop:
	@-docker rm -f $(IMAGE_NAME)

logs:
	docker logs -f $(IMAGE_NAME)

enter:
	docker exec -it $(IMAGE_NAME) sh

push:
	docker push ${IMAGE_PATH}

clean:
	docker rmi -f ${IMAGE_PATH}

test:
	tox
