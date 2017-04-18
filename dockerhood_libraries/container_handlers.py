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
The container_handlers module stores all the functions that create, destroy,
start and stop the docker containers.
"""

import logging

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.exceptions import LinkerAlreadyStarted, ImageMissing,\
    LinkerAlreadyStopped, LinkerNotFound, ContainerAlreadyStarted,\
    OnlyOneInstanceAllowed, WorkerNotFound, ContainerNotFound, QueueIsFull,\
    ContainerAlreadyStopped, WorkerAlreadyStarted, WorkerAlreadyStopped,\
    InvalidHostname, InvalidQueue
from dockerhood_libraries.docker_utilities import container_list, \
    active_container_list
from dockerhood_libraries.image_checks import slurm_master_image_exists, \
    worker_image_exists_for_queue, job_submitter_image_exists_for_queue, \
    linker_image_exists
from dockerhood_libraries.container_checks import linker_is_running,\
    linker_exists, slurm_master_host, slurm_master_is_running, worker_list,\
    job_submitter_host_for_queue, job_submitter_is_running_for_queue


__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


def start_linker():
    """
    Activate a linker container. If a container is already present, it will
    be started. Otherwise, it will be created and then started.
    """
    LOGGER.info('Starting linker')
    if linker_is_running():
        raise LinkerAlreadyStarted('A linker container is already running')

    LOGGER.debug('Connecting with {}'.format(config.running_linker_host.name))
    docker_client = config.running_linker_host.get_docker_client()

    # If the linker container does not exist, it must be created
    if not linker_exists():
        LOGGER.debug('A linker container does not exists and must be created')
        if not linker_image_exists(docker_client):
            linker_host_name = config.running_linker_host.name
            raise ImageMissing(
                'The {}_linker image is missing on the host {}, which is '
                'expected to run the linker'
                .format(config.project, linker_host_name)
            )

        # Create a list with all the ports that must be binded and a
        # dictionary with the number of the port inside and outside the
        # docker
        static_net_port = config.static_network.port
        ports = [static_net_port, ]
        port_bindings = {static_net_port: static_net_port}
        for q in config.queues:
            ports.append(q.port)
            port_bindings[q.port] = q.port
        LOGGER.debug(
            'The following ports will be bound to the linker: {}'.format(ports)
        )

        h_cfg = docker_client.create_host_config(
            port_bindings=port_bindings,
            privileged=True,
        )

        LOGGER.debug('Creating linker container')
        docker_client.create_container(
            image='{}_linker'.format(config.project),
            name='{}_linker'.format(config.project),
            hostname='linker',
            detach=True,
            ports=ports,
            host_config=h_cfg,
        )

    docker_client.start('{}_linker'.format(config.project))
    LOGGER.info('Linker started')


def stop_linker():
    """
    Stop the running linker container
    """
    LOGGER.info('Stopping linker')
    if not linker_is_running():
        raise LinkerAlreadyStopped('No linker container is running')

    if not linker_exists():
        raise LinkerNotFound('No linker container found')

    LOGGER.debug('Connecting with {}'.format(config.running_linker_host.name))
    docker_client = config.running_linker_host.get_docker_client()

    docker_client.stop('{}_linker'.format(config.project))
    LOGGER.info('Linker stopped')


def delete_linker():
    """
    Delete the linker container. If the container is running, it will
    be stopped and then deleted.
    """
    LOGGER.info('Deleting linker')

    if not linker_exists():
        raise LinkerNotFound('No linker container found on host')

    if linker_is_running():
        LOGGER.debug('Linker container is running: it will be stopped')
        stop_linker()

    LOGGER.debug('Connecting with {}'.format(config.running_linker_host.name))
    docker_client = config.running_linker_host.get_docker_client()

    docker_client.remove_container('{}_linker'.format(config.project))
    LOGGER.info('Linker deleted')


def start_slurm_master(host_name):
    """
    Activate a slurm master container. If a container is already present on
    the specified machine, it will just be started. Otherwise, it will be
    created and then started. It will raise an exception if a slurm_master is
    already created on another host

    Args:
        - host_name (str): the name of the host where the slurm master will
          be created
    """
    host_name = host_name.lower()
    LOGGER.info('Creating a slurm master docker on the {} host'
                ''.format(host_name))
    valid_hosts = [
        host for host in config.hosts if host.name.lower() == host_name
    ]

    if len(valid_hosts) == 0:
        raise InvalidHostname('No host called {}'.format(host_name))

    host = valid_hosts[0]
    docker_client = host.get_docker_client()

    already_created_on = slurm_master_host()
    if already_created_on is None:
        LOGGER.debug('No container for slurm master found. A new one will '
                     'be created!')

        if not slurm_master_image_exists(docker_client):
            raise ImageMissing('The {}_slurm_image is missing on the {} '
                               'host'.format(config.project, host.name))

        h_cfg = docker_client.create_host_config(privileged=True)
        image_name = '{}_slurm_master'.format(config.project)
        docker_client.create_container(
                                       image=image_name,
                                       name=image_name,
                                       hostname='slurm-master',
                                       detach=True,
                                       host_config=h_cfg,
                                       )
        LOGGER.debug('Starting the container {}_slurm_master'
                     ''.format(config.project))
        docker_client.start('{}_slurm_master'.format(config.project))

    elif already_created_on == host:
        LOGGER.debug("There is already a slurm master on {}. Let's try "
                     "to start it!".format(host.name))

        container_name = '{}_slurm_master'.format(config.project)
        if container_name in active_container_list(docker_client):
            raise ContainerAlreadyStarted('{} is already running on {}'
                                          ''.format(container_name, host.name))

        LOGGER.debug('The slurm master is not running on {}'.format(host.name))
        docker_client.start(container_name)

    else:
        raise OnlyOneInstanceAllowed('A slurm master instance has already '
                                     'been created on the {} host. Destroy '
                                     'it before trying to build another one '
                                     'on the {} host!'
                                     ''.format(already_created_on.name,
                                               host.name))

    LOGGER.info('Slurm master is running')


def stop_slurm_master():
    """
    Stop the running slurm master container
    """
    LOGGER.info('Stopping slurm_master')
    if not slurm_master_is_running():
        raise ContainerAlreadyStopped('The slurm master container is not '
                                      'running')

    LOGGER.debug('Checking on which host the slurm master container is '
                 'running')
    host = slurm_master_host()
    if host is None:
        raise ContainerNotFound('No slurm master container found!')
    LOGGER.debug('Found slurm master on {}'.format(host.name))

    LOGGER.debug('Connecting with {}'.format(host.name))
    docker_client = host.get_docker_client()

    docker_client.stop('{}_slurm_master'.format(config.project))
    LOGGER.info('Slurm master stopped')


def delete_slurm_master():
    """
    Delete the slurm_master container. If the container is running, it will
    be stopped and then deleted.
    """
    LOGGER.info('Deleting slurm master')

    host = slurm_master_host()
    if host is None:
        raise ContainerNotFound('No slurm master container found!')

    if slurm_master_is_running():
        LOGGER.debug('Slurm master container is running: it will be stopped')
        stop_slurm_master()

    LOGGER.debug('Connecting with {}'.format(host.name))
    docker_client = host.get_docker_client()

    docker_client.remove_container('{}_slurm_master'.format(config.project))
    LOGGER.info('Slurm master deleted')


def create_worker(queue, host_name):
    """
    Create a new worker container

    Args:
        - queue (str): the queue the new container will belong to
        - host_name (str): the machine that will host the new container

    Returns:
        The name of the new worker
    """
    LOGGER.info('Creating a worker for the queue {} on the host {}'
                ''.format(queue, host_name))
    queue = queue.lower().replace(' ', '-').replace('_', '-')
    LOGGER.debug('Looking for a queue named {}'.format(queue))
    if len([q for q in config.queues if q.name == queue]) == 0:
            raise InvalidQueue('Queue {} not found'.format(queue))
    LOGGER.debug('Queue named {} found'.format(queue))

    host_name = host_name.lower()
    LOGGER.debug('Looking for a host named {}'.format(host_name))
    valid_hosts = [h for h in config.hosts if h.name == host_name]
    if len(valid_hosts) == 0:
        raise InvalidHostname('Host {} not found'.format(host_name))
    host = valid_hosts[0]
    docker_client = host.get_docker_client()
    LOGGER.debug('Host named {} found'.format(host.name))

    # Prepare the new worker name
    name_start = config.project + '_'
    name_middle = queue
    name_end = '_worker'
    LOGGER.debug("The worker's name will have this structure: {}{}{}\\d\\d\\d "
                 '(\\d are digits)'.format(name_start, name_middle, name_end))

    workers = worker_list()
    for i in range(1, 255):
        name_attempt = name_start + name_middle + name_end + '{:0>3}'.format(i)
        if name_attempt not in [w['ext name'] for w in workers]:
            LOGGER.debug('The name "{}" is not in use. It will be used for '
                         'this container.'.format(name_attempt))
            container_name = name_attempt
            break
    else:
        raise QueueIsFull('The queue {} is full. No other machines can be '
                          'created in this queue'.format(queue))

    LOGGER.debug('Check if an image exists for queue {} on host {}'
                 ''.format(queue, host_name))
    if not worker_image_exists_for_queue(queue, docker_client):
        raise ImageMissing('The image for the queue {} is missing on the {} '
                           'host'.format(queue, host.name))

    LOGGER.debug('Creating the container {}'.format(container_name))
    h_cfg = docker_client.create_host_config(privileged=True)
    image_name = config.project + '_' + queue + '_worker'
    docker_client.create_container(
        image=image_name,
        name=container_name,
        detach=True,
        host_config=h_cfg,
    )

    LOGGER.debug('Starting the container {} on host {}'
                 ''.format(container_name, host.name))
    docker_client.start(container_name)

    sed_cmd = "sed -i 's/UNSPECIFIED/{}/g' /DOCKER_NAME.txt" \
              ''.format(container_name)
    LOGGER.debug('Making the container {} aware of its name using the '
                 'following command: {}'.format(container_name, sed_cmd))
    exec_id = docker_client.exec_create(container_name, sed_cmd)
    docker_client.exec_start(exec_id, stream=False)

    LOGGER.info('Worker {} as been created for the queue {} on the host {}'
                ''.format(container_name, queue, host_name))
    return container_name


def start_worker(worker_name):
    """
    Start again a stopped worker

    Args:
        - worker_name: A stopped worker
    """
    LOGGER.info('Starting worker {}'.format(worker_name))

    workers = [w for w in worker_list() if w['ext name'] == worker_name]
    if len(workers) == 0:
        raise WorkerNotFound('Worker {} not found'.format(worker_name))

    worker = workers[0]

    if worker['active'] is True:
        raise WorkerAlreadyStarted('The worker {} is already running. There '
                                   'is no need to start it again'
                                   ''.format(worker_name))

    host = worker['host']
    LOGGER.debug('The worker {} is running on host {}'
                 ''.format(worker_name, host.name))
    docker_client = host.get_docker_client()

    LOGGER.debug('Sending the start command for the container {} on the host '
                 '{}'.format(worker_name, host.name))
    docker_client.start(worker_name)

    LOGGER.info('Worker {} started'.format(worker_name))


def stop_worker(worker_name):
    """
    Stop a running worker

    Args:
        - worker_name: A stopped worker
    """
    LOGGER.info('Stopping worker {}'.format(worker_name))

    workers = [w for w in worker_list() if w['ext name'] == worker_name]
    if len(workers) == 0:
        raise WorkerNotFound('Worker {} not found'.format(worker_name))

    worker = workers[0]

    if worker['active'] is False:
        raise WorkerAlreadyStopped('The worker {} is already stopped. There '
                                   'is no need to stop it again'
                                   ''.format(worker_name))

    host = worker['host']
    LOGGER.debug('The worker {} is running on host {}'
                 ''.format(worker_name, host.name))
    docker_client = host.get_docker_client()

    LOGGER.debug('Sending the stop command for the container {} on the host '
                 '{}'.format(worker_name, host.name))
    docker_client.stop(worker_name)

    LOGGER.info('Worker {} stopped'.format(worker_name))


def delete_worker(worker_name):
    """
    Delete an existing worker

    Args:
        - worker_name: A stopped worker
    """
    LOGGER.info('Deleting worker {}'.format(worker_name))

    workers = [w for w in worker_list() if w['ext name'] == worker_name]
    if len(workers) == 0:
        raise WorkerNotFound('Worker {} not found'.format(worker_name))

    worker = workers[0]
    if worker['active'] is True:
        LOGGER.debug('Worker {} is running: it will be stopped!'
                     ''.format(worker_name))
        stop_worker(worker_name)

    LOGGER.debug('Connecting with {}'.format(worker['host'].name))
    docker_client = worker['host'].get_docker_client()

    docker_client.remove_container(worker_name)

    LOGGER.info('Worker {} deleted'.format(worker_name))


def stop_all_workers(queue=None, host_name=None):
    """
    Stop *ALL* workers that are managed by Dockerhood

    Args:
        - queue (str): if specified, stop only the workers of the selected
          queue
        - host_name (str): if specified, stop only the workers that are
          running on that host
    """
    message = 'Stopping all workers'
    if queue is not None:
        message += ' of the queue {}'.format(queue)
    if host_name is not None:
        message += ' that are running on the host {}'.format(host_name)
    LOGGER.info(message)

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

    workers = worker_list(queue=queue, host_name=host_name)

    active_workers = [w for w in workers if w['active'] is True]
    LOGGER.debug('{} workers must be stopped'.format(len(active_workers)))

    for worker in active_workers:
        LOGGER.debug('Stopping worker {}'.format(worker['ext name']))
        stop_worker(worker['ext name'])

    message = 'All workers'
    if queue is not None:
        message += ' of the queue {}'.format(queue)
    if host_name is not None:
        message += ' running on the host {}'.format(host_name)
    message += ' have been stopped'
    LOGGER.info(message)


def delete_all_workers(queue=None, host_name=None):
    """
    Delete *ALL* workers that are managed by Dockerhood

    Args:
        - queue (str): if specified, delete only the workers of the selected
          queue
        - host_name (str): if specified, delete only the workers that are
          running on that host
    """
    message = 'Deleting all workers'
    if queue is not None:
        message += ' of the queue {}'.format(queue)
    if host_name is not None:
        message += ' that are running on the host {}'.format(host_name)
    LOGGER.info(message)

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

    workers = worker_list(queue=queue, host_name=host_name)

    LOGGER.debug('{} workers will be deleted'.format(len(workers)))

    for worker in workers:
        LOGGER.debug('Deleting worker {}'.format(worker['ext name']))
        delete_worker(worker['ext name'])

    message = 'All workers'
    if queue is not None:
        message += ' of the queue {}'.format(queue)
    if host_name is not None:
        message += ' running on the host {}'.format(host_name)
    message += ' have been deleted'
    LOGGER.info(message)


def start_job_submitter(queue_name, host_name):
    """
    Activate a job submitter container. If a container for the specified queue
    is already present on the specified machine, it will just be started.
    Otherwise, it will be created and then started. It will raise an exception
    if a job submitter for that queue has already been created on another host

    Args:
        - queue_name (str): the name of the queue for which the container is
          created
        - host_name (str): the name of the host where the slurm master will
          be created
    """
    queue_name = queue_name.lower().replace(' ', '-').replace('_', '-')
    host_name = host_name.lower()

    LOGGER.info('Starting a job submitter container for the queue {} on the {} '
                'host'.format(queue_name, host_name))
    valid_hosts = [
        host for host in config.hosts if host.name.lower() == host_name
    ]

    if len(valid_hosts) == 0:
        raise InvalidHostname('No host called {}'.format(host_name))

    host = valid_hosts[0]
    docker_client = host.get_docker_client()

    already_created_on = job_submitter_host_for_queue(queue_name)
    if already_created_on is None:
        LOGGER.debug('No job submitter for queue {} found. A new one will '
                     'be created!'.format(queue_name))

        if not job_submitter_image_exists_for_queue(queue_name, docker_client):
            raise ImageMissing('The {}_{}_job_submitter image is missing on '
                               'the {} host'.format(config.project,
                                                    queue_name,
                                                    host.name))

        h_cfg = docker_client.create_host_config(privileged=True)
        image_name = '{}_{}_job_submitter'.format(config.project, queue_name)
        hostname = '{}-job-submitter'.format(queue_name)
        docker_client.create_container(
                                       image=image_name,
                                       name=image_name,
                                       hostname=hostname,
                                       detach=True,
                                       host_config=h_cfg,
                                       )
        LOGGER.debug('Starting the container {}_{}_job_submitter'
                     ''.format(config.project, queue_name))
        docker_client.start(image_name)

    elif already_created_on == host:
        LOGGER.debug("There is already a job submitter for the queue {} on {}. "
                     "Let's try to start it!".format(queue_name, host.name))

        container_name = '{}_{}_job_submitter'.format(config.project,
                                                      queue_name)
        if container_name in active_container_list(docker_client):
            raise ContainerAlreadyStarted('{} is already running on {}'
                                          ''.format(container_name, host.name))

        LOGGER.debug('The job submitter for the queue {} is not running on {}'
                     ''.format(queue_name, host.name))
        docker_client.start(container_name)

    else:
        raise OnlyOneInstanceAllowed(
            'A job submitter for the queue {} has already been created on the '
            '{} host. Destroy it before trying to build another one on the {} '
            'host!'.format(queue_name, already_created_on.name, host.name)
        )

    LOGGER.info('Job submitter for queue {} is running on {}'
                ''.format(queue_name, host.name))


def stop_job_submitter_for_queue(queue_name):
    """
    Stop the job submitter for the specified queue

    Args:
        - queue_name (str): the name of the queue
    """
    queue_name = queue_name.lower().replace(' ', '-').replace('_', '-')

    LOGGER.info('Stopping job submitter for queue {}'.format(queue_name))
    if not job_submitter_is_running_for_queue(queue_name):
        raise ContainerAlreadyStopped('The job submitter container of the '
                                      'queue {} is already stopped!'
                                      ''.format(queue_name))

    LOGGER.debug('Checking on which host the job submitter container of the '
                 'queue {} is running'.format(queue_name))
    host = job_submitter_host_for_queue(queue_name)
    if host is None:
        raise ContainerNotFound('No job submitter container found for queue {}'
                                ''.format(queue_name))
    LOGGER.debug('Found job submitter for queue {} on {}'
                 ''.format(queue_name, host.name))

    LOGGER.debug('Connecting with {}'.format(host.name))
    docker_client = host.get_docker_client()

    docker_client.stop('{}_{}_job_submitter'.format(config.project, queue_name))
    LOGGER.info('Job submitter for queue {} stopped'.format(queue_name))


def delete_job_submitter_for_queue(queue_name):
    """
    Delete the job submitter container for the specified queue. If the container
    is running, it will be stopped and then deleted.
    """
    queue_name = queue_name.lower().replace(' ', '-').replace('_', '-')
    LOGGER.info('Deleting job submitter for queue {}'.format(queue_name))

    host = job_submitter_host_for_queue(queue_name)
    if host is None:
        raise ContainerNotFound('No job submitter container found for queue {}!'
                                ''.format(queue_name))

    if job_submitter_is_running_for_queue(queue_name):
        LOGGER.debug('Job submitter for queue {} is running: it will be stopped'
                     ''.format(queue_name))
        stop_job_submitter_for_queue(queue_name)

    LOGGER.debug('Connecting with {}'.format(host.name))
    docker_client = host.get_docker_client()

    docker_client.remove_container('{}_{}_job_submitter'
                                   ''.format(config.project, queue_name))
    LOGGER.info('Job submitter for queue {} deleted'.format(queue_name))


def delete_all_containers():
    """
    Delete *ALL* containers that are managed by Dockerhood
    """
    LOGGER.info('Deleting all containers')

    for q in config.queues:
        if job_submitter_host_for_queue(q.name) is not None:
            delete_job_submitter_for_queue(q.name)
        else:
            LOGGER.debug('No job submitter found for queue {}. It will not be '
                         'deleted'.format(q.name))

    delete_all_workers()

    if slurm_master_host() is None:
        LOGGER.debug('Slurm master not found! It will not be deleted')
    else:
        delete_slurm_master()

    if linker_exists():
        delete_linker()
    else:
        LOGGER.debug('Linker not found! It will not be deleted')

    LOGGER.info('All containers have been deleted!')
