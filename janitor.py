#!/usr/bin/env python2

import os
import re
import time
import sys
import etcd
import docker
import logging

from pythonjsonlogger import jsonlogger
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.DEBUG)
if os.environ.get('FORMATTER', 'json') == 'json':
    default_format = '%(message)s,' \
                     '%(funcName)s,' \
                     '%(levelname)s,' \
                     '%(lineno)s,' \
                     '%(asctime)s,' \
                     '%(module)s'
    log_format = os.environ.get('LOG_FORMAT', default_format)
    formatter = jsonlogger.JsonFormatter(fmt=log_format)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    root_log = logging.getLogger()
    root_log.handlers = []
    root_log.addHandler(handler)
log = logging.getLogger(__name__)


SERVICES_PATH = '/deis/services/'
EXCLUDE_IMAGES_LIST = ['deis/(registry|publisher|builder|controller)',
                       'janitor',
                       'alpine']


class Janitor:
    def __init__(self, docker_client, etcd_client=False,
                 delete_images=False,
                 delete_containers=False,
                 version_max_count=3):
        self.etcd = etcd_client
        self.docker = docker_client
        self.delete_images = delete_images
        self.delete_containers = delete_containers
        self.version_max_count = version_max_count
        self.images = self.docker.images()
        if self.etcd:
            self.containers = self.docker.containers(
                all=True, filters={'status': 'exited'})
            self.apps = self.get_current_apps()

    def get_current_apps(self):
        apps = {}
        try:
            response = self.etcd.read(SERVICES_PATH,
                                      recursive=True,
                                      sorted=True)
        except KeyError as e:
            log.error({'error': str(e)})
            return {}
        for child in response.children:
            app = child.key.replace(SERVICES_PATH, '')
            if child.dir and len(child._children) == 0:
                apps[app] = 0
            try:
                app_name, instance = app.split('/')
                app_name, spec = instance.split('_v')
                version, service, inst = spec.split('.')
                apps[app_name] = int(version)
            except ValueError as e:
                log.warn({'warn': 'Unable to parse '
                                  'string "{}": {}'.format(app, e)})

        return apps

    @staticmethod
    def parse_tag(tag):
        pattern = re.compile(
            '^(?P<host>.[^\/]*)?\/(?P<name>.*):v(?P<version>[a-zA-Z0-9]+)$')
        match = pattern.match(tag)
        if match is None:
            return None
        return match.groupdict()

    @staticmethod
    def is_git_tag(tag):
        pattern = re.compile('^.*:git-[a-zA-Z\d]*$')
        match = pattern.match(tag)
        if match is None:
            return False
        return True

    def is_image_old(self, data):
        for app, version in self.apps.items():
            if data['name'] == app:
                if version == 0:
                    log.info('App "{}" does not exist '
                             'or has not running containers, all its '
                             'images need to be deleted'.format(app))
                    return True
                if version - self.version_max_count >= int(data['version']):
                    log.info('Current version of app: "{}:v{}"'.format(
                        app, version))
                    return True
        return False

    def delete_image(self, image):
        if not self.delete_images:
            log.info('Need to delete next image: {}'.format(image['Id']))
            return True

        log.info('Deleting image: Id:"{}", Tags:"{}"'.format(
            image['Id'],
            image['RepoTags']))
        try:
            log.info(self.docker.remove_image(image['Id'], force=True))
        except Exception as e:
            log.error({
                'error': 'Error during '
                         'deleting image "{}": {}'.format(image['Id'], e)})
            return False
        return True

    def delete_unused_images(self):
        for image in self.images:
            for tag in image['RepoTags']:
                if tag == '<none>:<none>':
                    log.info('Image: id="{}", RepoTags="{}" have not tag, '
                             'deleting'.format(image['Id'], image['RepoTags']))
                    self.delete_image(image)
                    continue
                if self.is_git_tag(tag):
                    log.info('Image: id="{}", RepoTags="{}" have git tag, '
                             'deleting'.format(image['Id'], image['RepoTags']))
                    self.delete_image(image)
                    continue
                data = self.parse_tag(tag)
                if data is not None:
                    log.debug(data)
                    if self.is_image_old(data):
                        self.delete_image(image)

    @staticmethod
    def is_image_in_exclude_list(image_name):
        for pattern in EXCLUDE_IMAGES_LIST:
            match = re.match(re.compile(pattern), image_name)
            if match is not None:
                return True
        return False

    def delete_cp_images(self):
        for image in self.images:
            for tag in image['RepoTags']:
                name = tag[:tag.index(':')]
                if not self.is_image_in_exclude_list(name):
                    self.delete_image(image)

    @staticmethod
    def filter_containers(containers):
        output = []
        filtered = {}
        for container in containers:
            if '/deis-builder' in container['Names']:
                filtered['builder'] = container
            elif '/deis-builder-data' in container['Names']:
                filtered['builder-data'] = container
            else:
                output.append(container)
        return output, filtered

    def delete_and_clean_builder(self, containers):
        if 'builder' in containers:
            log.debug('Delete container: name="{}", Status="{}"'.format(
                containers['builder']['Names'],
                containers['builder']['Status']))
            if self.delete_containers:
                self.delete_container(containers['builder']['Id'])
                self.delete_container(containers['builder-data']['Id'])
        else:
            log.info('(!) Builder is alive or not present, skip deleting')

    def delete_container(self, c_id):
        try:
            log.info(self.docker.remove_container(c_id, v=True))
        except Exception as e:
            log.error({'error': 'Error on deleting '
                                'container: "{}": {}'.format(c_id, e)})

    def delete_exited_containers(self):
        containers, filtered = self.filter_containers(self.containers)
        log.info('Processing regular containers')
        for container in containers:
            log.info('Delete container: name="{}", Status="{}"'.format(
                container['Names'], container['Status']))
            if self.delete_containers:
                self.delete_container(container['Id'])
        log.info('Processing builder containers')
        self.delete_and_clean_builder(filtered)


def main():
    etcd_client = False
    if not os.environ.get('CP_NODE', False):
        etcd_client = etcd.Client(
            host=os.environ.get('ETCD_HOST', '127.0.0.1'),
            version_prefix='/v2')

    docker_client = docker.Client(
        base_url=os.environ.get('DOCKER_URL', 'unix:///var/run/docker.sock'),
        version=os.environ.get('DOCKER_VERSION', 'auto'),
        timeout=int(os.environ.get('DOCKER_TIMEOUT', 300)))

    janitor = Janitor(
        etcd_client=etcd_client,
        docker_client=docker_client,
        delete_images='1' == os.environ.get('DELETE_IMAGES', '0'),
        version_max_count=int(os.environ.get('VERSION_MAX_COUNT', 3)),
        delete_containers='1' == os.environ.get('DELETE_CONTAINERS', '0')
    )

    if os.environ.get('CP_NODE', False):
        janitor.delete_cp_images()
    else:
        janitor.delete_exited_containers()
        janitor.delete_unused_images()

if __name__ == '__main__':
    if os.environ.get('RUN_ONCE', False) == 'True':
        log.info('Running in RUN_ONCE mode (execute one iteration and exit).')
        main()
        log.info('RUN_ONCE operation finished, so - exit.')
        exit(0)
    try:
        day = os.environ.get('CRON_DAY', '*')
        week = os.environ.get('CRON_WEEK', '*')
        day_of_week = os.environ.get('CRON_DAY_OF_WEEK', '*')
        hour = os.environ.get('CRON_HOUR', '*')
        minute = os.environ.get('CRON_MINUTE', '0')
        scheduler = BackgroundScheduler()
        scheduler.add_job(main,
                          'cron',
                          year='*',
                          month='*',
                          day=day,
                          week=week,
                          day_of_week=day_of_week,
                          hour=hour,
                          minute=minute,
                          second='0')
        scheduler.start()
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit) as e:
        log.info('Exiting due to KeyboardInterrupt or SystemExit')
