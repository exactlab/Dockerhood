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
The container_checks module stores all the functions that report the status
of the containers of the different hosts. This is different from the
container_handlers module which stores the functions that change the status
of the containers.
"""

import logging
import re

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.exceptions import InvalidQueue, InvalidHostname
from dockerhood_libraries.docker_utilities import container_list, \
                                               active_container_list,\
                                               get_container_hostname

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


def linker_exists():
    """
    Check if the linker container has been created

    Returns:
        True if exists a container called "PROJECTNAME_linker" on the machine
        that must run the linker, False otherwise
    """
    docker_client = config.running_linker_host.get_docker_client()
    container_name = '{}_linker'.format(config.project)
    return container_name in container_list(docker_client)


def linker_is_running():
    """
    Check if the linker container is running

    Returns:
        True if a container called "PROJECTNAME_linker" is running on the
        machine specified in the configuration files, False otherwise
    """
    docker_client = config.running_linker_host.get_docker_client()
    container_name = '{}_linker'.format(config.project)
    return container_name in active_container_list(docker_client)


def slurm_master_host():
    """
    Return the machine that is hosting the slurm master container. Return
    none if the slurm master container has not been created.

    Returns:
        An Host object that represent the machine hosting a container called
        "PROJECTNAME_slurm_master". None if such a container is not found.
    """

    for host in config.hosts:
        LOGGER.debug('Connecting to host {}'.format(host.name))
        docker_client = host.get_docker_client()

        host_containers = container_list(docker_client)
        container_name = '{}_slurm_master'.format(config.project)
        if container_name in host_containers:
            return host

    return None


def slurm_master_is_running():
    """
    Return a boolean that reports if the slurm master docker is running

    Returns:
        True if the slurm master docker is running, False otherwise
    """

    host = slurm_master_host()

    if host is None:
        LOGGER.debug('No slurm container found. Returning False')
        return False

    LOGGER.debug('The slurm master container is running on {}'
                 ''.format(host.name))
    host_docker_client = host.get_docker_client()
    container_name = '{}_slurm_master'.format(config.project)
    return container_name in active_container_list(host_docker_client)


def worker_list(queue=None, host_name=None, only_active=False):
    """
    Return a list of all the workers. A worker is returned as a dictionary
    with the following fields:
    - 'ext name': the name of the docker container
    - 'int name': the hostname of the docker machine
    - 'queue': the queue the container belongs to
    - 'active': True if the docker is running, False otherwise
    - 'host': the host where the container is running (as an Host object)

    Args:
        - queue (str): if specified, return only the workers of the selected
          queue
        - host_name (str): if specified, return only the workers that are
          running on that host
        - only_active (bool): return only the the workers that are in active
          state (by default is False)

    Returns:
        A list of dictionaries. Each dictionary describes a worker.
    """

    if queue is not None:
        queue = queue.lower().replace(' ', '-').replace('_', '-')
        LOGGER.debug('Looking for a queue named {}'.format(queue))
        if len([q for q in config.queues if q.name == queue]) == 0:
            raise InvalidQueue('Queue {} not found'.format(queue))
        LOGGER.debug('Queue named {} found'.format(queue))

    if host_name is not None:
        host_name = host_name.lower()
        LOGGER.debug('Looking for a host named {}'.format(host_name))
        if len([h for h in config.hosts if h.name == host_name]) == 0:
            raise InvalidHostname('Host {} not found'.format(host_name))

    # Create a regular expression such that if a container is a worker it
    # will be recognized by the regexp
    start_string = config.project + '_'
    if queue is None:
        middle_string = '(?P<queue>[^_]*)'
    else:
        middle_string = queue
    end_string = '_worker\d\d\d'
    worker_mask = start_string + middle_string + end_string
    LOGGER.debug('Looking for containers that match the following regexp: {}'
                 ''.format(worker_mask))
    worker_mask = re.compile(worker_mask)

    wrk_list = []
    for host in config.hosts:
        if host_name is None or host_name == host.name:
            LOGGER.debug('Connecting to host {}'.format(host.name))
            host_client = host.get_docker_client()
            containers_in_host = container_list(host_client)
            active_containers_in_host = active_container_list(host_client)
            for container in containers_in_host:
                container_match = worker_mask.match(container)
                if container_match:
                    worker = {
                        'ext name': container,
                        'host': host,
                        'active': container in active_containers_in_host,
                    }

                    if queue is None:
                        worker['queue'] = container_match.group('queue')
                    else:
                        worker['queue'] = queue

                    if worker['active'] == True:
                        worker['int name'] = get_container_hostname(
                            container,
                            host_client
                        )
                    else:
                        worker['int name'] = None

                    if only_active == False or worker['active'] == True:
                        wrk_list.append(worker)

    return wrk_list


def job_submitter_host_for_queue(queue):
    """
    Return the machine that is hosting the job submitter container for the
    specified queue. Returns None if this container has not been created.

    Args:
        - queue (str): the name of the queue

    Returns:
        An Host object that represent the machine hosting a container called
        "PROJECTNAME_QUEUENAME_job_submitter". None if such a container is not
        found.
    """
    queue = queue.lower().replace(' ', '-').replace('_', '-')
    LOGGER.debug('Looking for a queue named {}'.format(queue))
    if len([q for q in config.queues if q.name == queue]) == 0:
        raise InvalidQueue('Queue {} not found'.format(queue))
    LOGGER.debug('Queue named {} found'.format(queue))

    for host in config.hosts:
        LOGGER.debug('Connecting to host {}'.format(host.name))
        docker_client = host.get_docker_client()

        host_containers = container_list(docker_client)
        container_name = '{}_{}_job_submitter'.format(config.project, queue)
        if container_name in host_containers:
            return host

    return None


def job_submitter_is_running_for_queue(queue):
    """
    Return a boolean that reports if the job submitter container is running
    for the specified queue

    Args:
        - queue (str): the name of the queue

    Returns:
        True if the job submitter container is running, False otherwise
    """
    queue = queue.lower().replace(' ', '-').replace('_', '-')
    host = job_submitter_host_for_queue(queue)

    if host is None:
        LOGGER.debug('No job submitter found for queue {}. Returning False'
                     ''.format(queue))
        return False

    LOGGER.debug('The job submitter container for queue is running on {}'
                 ''.format(queue, host.name))
    host_docker_client = host.get_docker_client()
    container_name = '{}_{}_job_submitter'.format(config.project, queue)
    return container_name in active_container_list(host_docker_client)
