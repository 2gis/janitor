import unittest
import json
import copy
from janitor import Janitor

# TODO Tests for builder deleting(when builder exited)


class EtcdKey:
    def __init__(self, key, dir, children=[]):
        self.key = key
        self.dir = dir
        self._children = children


class EtcdResponse:
    def __init__(self, children):
        self.children = children


class EtcdMockRaise:
    def read(self, path, recursive=None, sorted=True):
        raise KeyError('Key "{}" doesn\'t exists'.format(path))


class EtcdMockEmpty:
    def read(self, path, recursive=None, sorted=True):
        return EtcdResponse([])


class EtcdMockCorrect:
    def read(self, path, recursive=None, sorted=True):
        data = [
            EtcdKey('/deis/services/my-shiny-service', dir=True),
            EtcdKey('/deis/services/shiny-service/shiny-service_v20.cmd.1',
                    dir=False),
            EtcdKey('/deis/services/shiny-service/shiny-service_v20.cmd.2',
                    dir=False),
            EtcdKey('/deis/services/madrobot/madrobot_v186.web.1',
                    dir=False),
            EtcdKey('/deis/services/madrobot/madrobot_v186.web.2',
                    dir=False),
            EtcdKey('/deis/services/madrobot/madrobot_v186.web.3',
                    dir=False),
            EtcdKey('/deis/services/madrobot/madrobot_v187.web.1',
                    dir=False),
        ]
        return EtcdResponse(data)


class DockerMock:
    def __init__(self):
        with open('mocks/docker_containers_mock.json', 'r') as f:
            self._containers = json.loads(f.read())
        with open('mocks/docker_images_mock.json', 'r') as f:
            self._images = json.loads(f.read())

    def containers(self, all=None, filters={}):
        return self._containers

    def images(self):
        return copy.deepcopy(self._images)

    def remove_image(self, c_id, force=None):
        for image in self._images:
            if image['Id'] == c_id:
                self._images.remove(image)
                return True
        raise Exception('This is not image with id: {}'.format(c_id))

    def remove_container(self, c_id, v=None):
        for container in self._containers:
            if container['Id'] == c_id:
                self._containers.remove(container)
                return True
        raise Exception('This is not container with id: {}'.format(c_id))


class TestJunitParser(unittest.TestCase):

    def test_get_current_apps_no_etcd_catalog(self):
        janitor = Janitor(etcd_client=EtcdMockRaise(),
                          docker_client=DockerMock())
        self.assertEqual({}, janitor.get_current_apps())

    def test_get_current_apps_empty_etcd_catalog(self):
        janitor = Janitor(etcd_client=EtcdMockEmpty(),
                          docker_client=DockerMock())
        self.assertEqual({}, janitor.get_current_apps())

    def test_get_current_apps_correct_app(self):
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=DockerMock())
        self.assertEqual({'madrobot': 187,
                          'my-shiny-service': 0, 'shiny-service': 20},
                         janitor.get_current_apps())

    def test_parse_tag(self):
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=DockerMock())
        self.assertEqual(janitor.parse_tag(''), None)
        self.assertEqual(janitor.parse_tag('host:v1'), None)
        self.assertEqual(janitor.parse_tag('host/name:v1'),
                         {'host': 'host', 'name': 'name', 'version': '1'})
        self.assertEqual(janitor.parse_tag('h-o-s-t/name1:v12'),
                         {'host': 'h-o-s-t', 'name': 'name1', 'version': '12'})

    def test_is_image_old(self):
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=DockerMock())
        self.assertFalse(janitor.is_image_old(
            {'name': 'shiny-service', 'version': 20}))
        self.assertFalse(janitor.is_image_old(
            {'name': 'shiny-service', 'version': '19'}))
        self.assertFalse(janitor.is_image_old(
            {'name': 'shiny-service', 'version': 18}))
        self.assertTrue(janitor.is_image_old(
            {'name': 'shiny-service', 'version': 17}))
        self.assertTrue(janitor.is_image_old(
            {'name': 'shiny-service', 'version': 0}))
        self.assertTrue(janitor.is_image_old(
            {'name': 'shiny-service', 'version': '0'}))

    def test_delete_image(self):
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=DockerMock())
        image = {'Id': 'myid'}
        self.assertTrue(janitor.delete_image(image))
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=DockerMock(), delete_images=True)
        image = {'Id': 'myid', 'RepoTags': []}
        self.assertFalse(janitor.delete_image(image))

    def test_delete_unused_images(self):
        dockermock = DockerMock()
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=dockermock, delete_images=1)
        count = len(dockermock.images())
        tags = 0
        for image in dockermock.images():
            tags = tags + len(image['RepoTags'])
        self.assertEqual(tags, 20)

        janitor.delete_unused_images()

        tags = 0
        for image in dockermock.images():
            tags = tags + len(image['RepoTags'])
        self.assertEqual(tags, 13)

        self.assertEqual(count - 5, len(dockermock.images()))

    def test_delete_exited_containers(self):
        dockermock = DockerMock()
        janitor = Janitor(etcd_client=EtcdMockCorrect(),
                          docker_client=dockermock, delete_containers=1)
        janitor.delete_exited_containers()
        # Do not delete last /deis-builder-data if builder not found in exited
        # containers
        self.assertEqual(len(dockermock.containers()), 1)
        self.assertEqual(dockermock.containers()[0]['Names'][0],
                         '/deis-builder-data')

    def test_delete_cp_images(self):
        dockermock = DockerMock()
        janitor = Janitor(docker_client=dockermock, delete_images=1)
        janitor.delete_cp_images()
        tags = 0
        for image in dockermock.images():
            tags = tags + len(image['RepoTags'])
        self.assertEqual(tags, 3)
