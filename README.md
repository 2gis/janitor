# Janitor

Janitor - an open-source GC tool for docker images in DEIS environment.

features: 
 - Keeps the latest version of the application for quick rollback
 - Able to clean docker images inside deis-builder

# Installation

Clone repository:
```bash
git clone https://github.com/2gis/janitor.git
cd janitor
```

Edit `REGISTRY` and `REGISTRY_PATH` in makefile:
```bash
vim makefile
```

Build docker image:
```bash
make build
```

Push image to your docker registry
```bash
make push
```

Install systemd-unit on DEIS node. Templates in `systemd` directory.  
Pre-change `Environment='IMAGE=my/janitor'` to you docker image path in systemd-unit.

# ENV variables

|Variable|Description|Default value|
| ------------- |:-------------:|:-----:|
|**CRON_DAY**|day for cron job start|*|
|**CRON_WEEK**|week for cron job start|*|
|**CRON_DAY_OF_WEEK**|day of week for cron job start|*|
|**CRON_HOUR**|hour for cron job start|*|
|**CRON_MINUTE**|minute for cron job start|0|
|**DELETE_IMAGES**|Remove docker image or not. 0 is no|0|
|**VERSION_MAX_COUNT**|the number of releases to save application-specific images|3|
|**DELETE_CONTAINERS**|Remove docker containers or not. 0 is no|0|
|**CP_NODE**|True, if run on the ControlPlane node|False|
|**ETCD_HOST**|entrypoint for connection to etcd2|'127.0.0.1'|
|**DOCKER_URL**|entrypoint for connection to Docker|'unix:///var/run/docker.sock'|
|**DOCKER_VERSION**|your version of Docker|'auto'|
|**DOCKER_TIMEOUT**|timeout for connection to Docker|300|

Default exclude images described in EXCLUDE_IMAGES_LIST. You can change it in janitor.py:
```python
EXCLUDE_IMAGES_LIST = ['deis/(registry|publisher|builder|controller)',
                       'janitor',
                       'alpine']
```

# Warning!

Do not set the `CP_NODE = True` on Data Plane nodes. Because in this case, the janitor remove all docker images on the node.
