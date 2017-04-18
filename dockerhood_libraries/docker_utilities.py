# This file is part of Dockerhood.
#
# Dockerhood is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Dockerhood is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Dockerhood. If not, see <http://www.gnu.org/licenses/>.
#

import re
import logging

from dockerhood_libraries.configuration_reader import config

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

# These are the masks for the StreamLine
STREAM_MASK = r'^\{"stream":"(?P<cont>.*?)(\\r\\n|\\n|\\r)?\"}'
STREAM_REGEXP = re.compile(STREAM_MASK)
ERROR_MASK = r'"error":"(?P<cont>.*?)"'
ERROR_REGEXP = re.compile(ERROR_MASK)

LOGGER = logging.getLogger(__name__)


class StreamLine(object):
    """
    Wrapper around a line of the stream from the docker client output
    """
    def __init__(self, bt):
        self.status = 'UNKNOWN'
        self.raw = bt.decode('ASCII')
        self.message = None

        stream_match = STREAM_REGEXP.match(self.raw)
        error_match = ERROR_REGEXP.search(self.raw)
        if stream_match:
            ascii_escaped = stream_match.group(1)
            data_str = ascii_escaped.encode('ASCII').decode('unicode-escape')
            self.message = data_str
            self.status = 'OK'
        elif error_match:
            ascii_escaped = error_match.group(1)
            data_str = ascii_escaped.encode('ASCII').decode('unicode-escape')
            self.message = data_str
            self.status = 'ERROR'
        else:
            LOGGER.warning('Unrecognized message: {}'.format(self.raw))


def image_list(docker_cli):
    """
    Return a list of all the docker image tags
    """
    imgs = docker_cli.images()
    return [img["RepoTags"][0] for img in imgs]


def image_exists(image_name, docker_cli):
    """
    Return True if an image with the image_name tag exists
    """
    if ':' not in image_name:
        image_name += ':latest'
    return image_name in image_list(docker_cli)


def container_list(docker_cli):
    """
    Return a list of all the names of the docker containers
    """
    return [cont['Names'][0][1:] for cont in docker_cli.containers(all=True)]


def active_container_list(docker_cli):
    """
    Return a list of all the names of the active docker containers
    """
    return [cont['Names'][0][1:] for cont in docker_cli.containers()]


def get_container_hostname(container_name, docker_cli):
    """
    Return the hostname of the specified docker container. This function
    will run the "hostname" command on the container and return its output
    """
    exec_id = docker_cli.exec_create(container_name, 'hostname')
    exec_output = docker_cli.exec_start(exec_id, stream=False)
    hostname = exec_output.decode('ASCII').strip('\n').strip('\r')
    return hostname


def test_hosts():
    """
    Run the "Hello Word" docker test on all the configured hosts
    """
    host_answers = {}

    LOGGER.info('Testing the hosts')
    for host in config.hosts:
        LOGGER.debug('Running on {}'.format(host.name))
        host_cli = host.get_docker_client()
        if 'hello-world' not in image_list(host_cli):
            LOGGER.debug('hello-world image not found. It will be downloaded')
            host_cli.pull('hello-world', 'latest')
            LOGGER.debug('Download executed')
        container = host_cli.create_container('hello-world')
        host_cli.start(container['Id'])
        host_cli.wait(container['Id'])
        host_answers[host] = host_cli.logs(container['Id']).decode('ASCII')
        host_cli.remove_container(container['Id'])
    LOGGER.info('Test executed')
    return host_answers
