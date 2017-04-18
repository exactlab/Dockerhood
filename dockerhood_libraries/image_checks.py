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

"""
The image_checks module stores all the functions that report the status
of the image archive of the different hosts. This is different from the
image_handlers module which stores the functions that change the status
of this archive.
"""

import logging
from os import path

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.docker_utilities import image_exists
from dockerhood_libraries.exceptions import InvalidQueue

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


def key_generator_exists(docker_client):
    """
    Check if an image for the the key generator docker exists

    Args:
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the image of the key generator exists, False otherwise
    """
    image_name = '{}_key_generator'.format(config.project)
    return image_exists(image_name, docker_client)


def linker_image_exists(docker_client):
    """
    Check if an image for the the linker docker exists

    Args:
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the image of the linker exists, False otherwise
    """
    image_name = '{}_linker:latest'.format(config.project)
    return image_exists(image_name, docker_client)


def base_image_exists(docker_client):
    """
    Check if a base image (the starting point for all the other images) exists

    Args:
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the base image exists, False otherwise
    """
    if config.base_image_is_a_template:
        img = '{}_base_image:latest'.format(config.project)
    else:
        img = config.base_image_name
    return image_exists(img, docker_client)


def slurm_master_image_exists(docker_client):
    """
    Check if an image for the the slurm master docker exists

    Args:
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the image of the slurm master exists, False otherwise
    """
    image_name = '{}_slurm_master'.format(config.project)
    return image_exists(image_name, docker_client)


def worker_image_exists_for_queue(queue, docker_client):
    """
    Check if an image for the worker exists for the specific queue

    Args:
        - queue (str): The name of the computational queue
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the image of a worker for the specific queue exists, False
        otherwise
    """
    LOGGER.debug('Looking for a queue named {}'.format(queue))
    selected_queue = [
        q for q in config.queues if q.name.lower() == queue.lower()
    ]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue))

    LOGGER.debug('Found {} queue(s) named {}'
                 ''.format(len(selected_queue), queue))
    selected_queue = selected_queue[0]
    q_name = selected_queue.name.lower()

    image_name = '{}_{}_worker'.format(config.project, q_name)
    return image_exists(image_name, docker_client)


def job_submitter_image_exists_for_queue(queue, docker_client):
    """
    Check if an image for the job submitter exists for the specific queue

    Args:
        - queue (str): The name of the computational queue
        - docker_client: a Client object from the docker library.
          It will be the interface used to communicate with the docker-engine
          and, therefore, it implicitly defines on which host the request is
          performed

    Returns:
        True if the image of a job submitter for the specific queue exists,
        False otherwise
    """
    LOGGER.debug('Looking for a queue named {}'.format(queue))
    selected_queue = [
        q for q in config.queues if q.name.lower() == queue.lower()
    ]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue))

    LOGGER.debug('Found {} queue(s) named {}'
                 ''.format(len(selected_queue), queue))
    selected_queue = selected_queue[0]
    q_name = selected_queue.name.lower()

    image_name = '{}_{}_job_submitter'.format(config.project, q_name)
    return image_exists(image_name, docker_client)


def check_keys():
    """
    Check if the keys for the VPNs have been successfully created

    Returns:
        True if the files with the keys have been generated inside the keys_dir
        of the machine that will build the images, False otherwise
    """
    keys_dir = config.keys_dir
    keys_file_list = [
                      'ca.crt',
                      'ca.key',
                      'dh2048.pem',
                      'linker-client.crt',
                      'linker-client.csr',
                      'linker-client.key',
                      'linker.crt',
                      'linker.csr',
                      'linker.key',
                      'ta.key'
                      ]
    for key_file in keys_file_list:
        key_path = path.join(keys_dir, key_file)
        LOGGER.debug('Looking for file {}'.format(key_path))
        if not path.exists(key_path):
            LOGGER.debug('File {} is missing. No valid keys found!'
                         ''.format(key_path))
            return False
        else:
            LOGGER.debug('File {} exists'.format(key_path))
    return True

