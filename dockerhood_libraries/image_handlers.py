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

from os import makedirs, path
import logging

from dockerhood_libraries.docker_utilities import image_list, image_exists,\
    container_list
from dockerhood_libraries.exceptions import ImageAlreadyBuilt, InvalidQueue,\
    BaseImageNotBuilt, ImageNotFound, ImageInUse, ImageNotFromATemplate
from dockerhood_libraries.image_checks import worker_image_exists_for_queue,\
    linker_image_exists, slurm_master_image_exists, base_image_exists,\
    key_generator_exists, job_submitter_image_exists_for_queue, check_keys

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.template_render import template_render

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


def delete_key_generator(docker_client):
    """
    Delete the image of the key generator
    """
    image_name = '{}_key_generator'.format(config.project)
    docker_client.remove_image(image_name)


def delete_base_image(docker_client):
    """
    Delete the base image
    """
    if not config.base_image_is_a_template:
        raise ImageNotFromATemplate(
            'The base image does not come from a template and therefore it is '
            'not managed by DockerHood'
        )
    if not base_image_exists(docker_client):
        raise BaseImageNotBuilt('Base image not found!')

    image_name = '{}_base_image'.format(config.project)
    LOGGER.debug('Deleting image {}'.format(image_name))
    docker_client.remove_image(image_name)


def delete_linker_image(docker_client):
    """
    Delete the image of the linker docker
    """
    image_name = '{}_linker'.format(config.project)

    if not linker_image_exists(docker_client):
        raise ImageNotFound('Linker image is missing and can not be '
                            'deleted (maybe it has already been deleted)')

    # Check if there is a container that uses the image
    linker_container_name = image_name
    if linker_container_name in container_list(docker_client):
        raise ImageInUse('A linker container exists. Remove it before '
                         'deleting its image')

    LOGGER.debug('Deleting image {}'.format(image_name))
    docker_client.remove_image(image_name)


def delete_slurm_master_image(docker_client):
    """
    Delete the image of the slurm master
    """
    if not slurm_master_image_exists(docker_client):
        raise ImageNotFound('Slurm master image is missing and can not be '
                            'deleted (maybe it has already been deleted)')

    # Check if there are some containers that use the image
    slurm_master_container = '{}_slurm_master'.format(config.project)
    if slurm_master_container in container_list(docker_client):
        raise ImageInUse('The slurm master container is using the slurm master '
                         'image. Remove that container before deleting the '
                         'image')

    image_name = '{}_slurm_master'.format(config.project)
    LOGGER.debug('Deleting image {}'.format(image_name))
    docker_client.remove_image(image_name)


def delete_worker_image_for_queue(queue, docker_client):
    """
    Delete the image of the worker of the selected queue
    """
    selected_queue = [q for q in config.queues
                              if q.name.lower() == queue.lower()]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue))

    selected_queue = selected_queue[0]

    q_name = selected_queue.name.lower()
    image_name = '{}_{}_worker'.format(config.project, q_name)

    if not worker_image_exists_for_queue(queue, docker_client):
        raise ImageNotFound('Image "{}" is missing and can not be deleted'
                            ''.format(image_name))

    # Check if there are some containers that use the image
    container_using_image = [cnt for cnt in container_list(docker_client)
                                 if cnt.startswith(image_name)]
    if len(container_using_image) > 0:
        raise ImageInUse('There is a container that is using the image "{}". '
                         'Remove it before deleting the image'
                         ''.format(image_name))

    LOGGER.debug('Deleting image {}'.format(image_name))
    docker_client.remove_image(image_name)


def delete_job_submitter_image_for_queue(queue, docker_client):
    """
    Delete the image of the worker of the selected queue
    """
    selected_queue = [q for q in config.queues
                      if q.name.lower() == queue.lower()]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue))

    selected_queue = selected_queue[0]

    q_name = selected_queue.name.lower()
    image_name = '{}_{}_job_submitter'.format(config.project, q_name)

    if not job_submitter_image_exists_for_queue(queue, docker_client):
        raise ImageNotFound('Image "{}" is missing and can not be deleted'
                            ''.format(image_name))

    # Check if there are some containers that use the image
    container_name = image_name
    if container_name in container_list(docker_client):
        raise ImageInUse('A container that uses the image "{}" exists. Remove '
                         'it before attempting to delete the image'
                         ''.format(image_name))

    LOGGER.debug('Deleting image {}'.format(image_name))
    docker_client.remove_image(image_name)


def create_key_generator(docker_client):
    """
    Create a docker image for the key generator
    """
    if key_generator_exists(docker_client):
        LOGGER.debug('Key generator image is already present and it will not '
                     'be rebuilt')
        return 0

    # Read the docker template
    template_render.render('key_generator',
                           None,
                           '{}_key_generator'.format(config.project),
                           docker_client
                           )


def create_base_image(docker_client):
    """
    Create a docker image that will be used as a base image for all the others
    templates
    """
    if not config.base_image_is_a_template:
        raise ImageNotFromATemplate(
            'The base image does not come from a template and therefore it can '
            'not be created by DockerHood'
        )
    if base_image_exists(docker_client):
        raise ImageAlreadyBuilt(
            'Base image is already present! Delete it before build it again'
        )
    LOGGER.debug(
        'Rendering base image from template {}'
        .format(config.base_image_name)
    )
    template_render.render(None,
                           config.base_image_name,
                           '{}_base_image'.format(config.project),
                           docker_client
                           )


def create_linker_image(docker_client):
    """
    Create a docker image for the linker
    """
    if linker_image_exists(docker_client):
        raise ImageAlreadyBuilt('Linker image is already present! '
                                'Delete it before build it again')
    if config.base_image_is_a_template and not base_image_exists(docker_client):
        raise BaseImageNotBuilt(
            'The base image has not be built. Please, build it before building '
            'any other image'
        )

    # Read the docker template
    template_render.render('linker',
                           None,
                           '{}_linker'.format(config.project),
                           docker_client
                           )


def create_slurm_master_image(docker_client):
    """
    Create a docker image for the slurm_master
    """
    if slurm_master_image_exists(docker_client):
        raise ImageAlreadyBuilt('Slurm master image is already present! '
                                'Delete it before build it again')
    if config.base_image_is_a_template and not base_image_exists(docker_client):
        raise BaseImageNotBuilt(
            'The base image has not be built. Please, build it before building '
            'any other image'
        )

    # Read the docker template
    template_render.render('slurm_master',
                           None,
                           '{}_slurm_master'.format(config.project),
                           docker_client
                           )


def create_worker_image_for_queue(queue_name, docker_client):
    """
    Create a docker image for the worker of the specified queue
    """
    selected_queue = [q for q in config.queues
                              if q.name.lower() == queue_name.lower()]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue_name))

    selected_queue = selected_queue[0]

    q_dict = dict()
    q_dict['Q_NAME'] = selected_queue.name
    q_dict['Q_PORT'] = str(selected_queue.port)
    q_dict['Q_SUBNET'] = selected_queue.network_ip.as_string()

    image_name = '{}_{}_worker'.format(config.project, q_dict['Q_NAME'].lower())

    if worker_image_exists_for_queue(queue_name, docker_client):
        raise ImageAlreadyBuilt('Worker image for queue {} is already '
                                'present! Delete it before build it again'
                                ''.format(queue_name.lower()))

    if config.base_image_is_a_template and not base_image_exists(docker_client):
        raise BaseImageNotBuilt(
            'The base image has not be built. Please, build it before building '
            'any other image'
        )

    # Read the docker template
    template_render.render('worker',
                           selected_queue.worker_template,
                           image_name,
                           docker_client,
                           q_dict
                           )


def create_job_submitter_image_for_queue(queue_name, docker_client):
    """
    Create a docker image for the job submitter of the specified queue
    """
    selected_queue = [q for q in config.queues
                              if q.name.lower() == queue_name.lower()]
    if len(selected_queue) == 0:
        raise InvalidQueue('Queue "{}" not found'.format(queue_name))

    selected_queue = selected_queue[0]

    q_dict = {'JOB_SUBMITTER_IP': selected_queue.job_submitter.ip.as_string()}

    image_name = '{}_{}_job_submitter'.format(config.project,
                                              selected_queue.name.lower())

    if job_submitter_image_exists_for_queue(queue_name, docker_client):
        raise ImageAlreadyBuilt('Job submitter image for queue {} is already '
                                'present! Delete it before build it again'
                                ''.format(queue_name.lower()))

    if config.base_image_is_a_template and not base_image_exists(docker_client):
        raise BaseImageNotBuilt(
            'The base image has not be built. Please, build it before building '
            'any other image'
        )

    # Read the docker template
    template_render.render('job_submitter',
                           selected_queue.job_submitter.user_template,
                           image_name,
                           docker_client,
                           q_dict
                           )


def create_worker_images(docker_client):
    """
    Create a docker image for the workers of each queue
    """
    for queue in config.queues:
        create_worker_image_for_queue(queue.name, docker_client)


def create_job_submitter_images(docker_client):
    """
    Create a docker image for the workers of each queue
    """
    for queue in config.queues:
        create_job_submitter_image_for_queue(queue.name, docker_client)


def copy_image(image, host_src, host_dest):
    """
    Copy an image from on host_src to host_dest

    Args:
        - image (str): The name of the image that must be copied
        - host_src: The host with the image (an Host object)
        - host_dest: The host where the image will be copied (an Host object)
    """
    LOGGER.info('Copying image {} from {} to {}'
                ''.format(image, host_src.name, host_dest.name))
    LOGGER.debug('Connecting to {}'.format(host_src.name))
    src_docker = host_src.get_docker_client()

    LOGGER.debug('Checking if {} has the image {}'
                 ''.format(host_src.name, image))
    if not image_exists(image, src_docker):
        raise ValueError('Host {} does not have the image {}. Copy failed!'
                         ''.format(host_src.name, image))

    LOGGER.debug('Connecting to {}'.format(host_src.name))
    dest_docker = host_dest.get_docker_client()

    LOGGER.debug('Checking if the image {} is already present on {} host'
                 ''.format(image, host_dest.name))
    if image_exists(image, dest_docker):
        raise ValueError('Host {} does already have the image {}. Copy failed!'
                         ''.format(host_dest.name, image))

    LOGGER.debug('Reading image {} from {}'
                 ''.format(image, host_src.name))
    src_image = src_docker.get_image(image).data

    LOGGER.debug('Saving image {} into {}'
                 ''.format(image, host_dest.name))
    dest_docker.load_image(src_image)


def create_keys():
    if not path.exists(config.keys_dir):
        try:
            makedirs(config.keys_dir)
        except OSError:
            raise OSError('ERROR: Unable to create the directory '
                          '{}'.format(config.keys_dir))

    im_builder_client = config.image_builder.get_docker_client()
    if not key_generator_exists(im_builder_client):
        create_key_generator(im_builder_client)

    key_generator_name = '{}_key_generator'.format(config.project)
    if key_generator_name in container_list(im_builder_client):
        LOGGER.warning('There is already a container named {}. Has an '
                       'execution been stopped during the creation of the '
                       'keys? In any case, the container will be removed'
                       ''.format(key_generator_name))
        im_builder_client.remove_container(key_generator_name)

    keydir = path.abspath(config.keys_dir)
    vol_binds = [ keydir + ':' + '/home/user/keys']
    host_config = im_builder_client.create_host_config(
                           binds=vol_binds,
                           restart_policy={
                                           "MaximumRetryCount": 0,
                                           "Name": "none"
                                           }
                           )
    cnt_id = im_builder_client.create_container(
                                                 image=key_generator_name,
                                                 name=key_generator_name,
                                                 volumes=['/home/user/keys'],
                                                 host_config=host_config,
                                                 )

    LOGGER.info('Generating keys')
    im_builder_client.start(cnt_id)
    docker_status = im_builder_client.wait(cnt_id)

    im_builder_client.remove_container(cnt_id)

    if docker_status == 0:
        LOGGER.info('Keys successfully generated!')
    else:
        raise Exception('Unknown error during the generation of the keys!')


def create_all_images():
    if not check_keys():
        raise Exception('Keys not generated! Please, generate the VPN keys '
                        'before building the images')

    LOGGER.debug('Connecting to the builder host')
    im_builder_client = config.image_builder.get_docker_client()

    if config.base_image_is_a_template:
        if not base_image_exists(im_builder_client):
            LOGGER.debug('Building base image')
            create_base_image(im_builder_client)
        else:
            LOGGER.debug(
                'Base image will not be built because it already exists'
            )

    LOGGER.debug('Building linker image')
    create_linker_image(im_builder_client)

    LOGGER.debug('Building slurm master image')
    create_slurm_master_image(im_builder_client)

    LOGGER.debug("Building workers' images")
    create_worker_images(im_builder_client)

    LOGGER.debug("Building job submitters' images")
    create_job_submitter_images(im_builder_client)

    # Create a list of the built images but the base_image
    project_images = [
        img for img in image_list(im_builder_client)
        if img.startswith(config.project + '_') and not
        img.startswith(config.project + '_base_image')
    ]

    LOGGER.debug('Sending images to all the other hosts')
    for host in config.hosts:
        if host is not config.image_builder:
            LOGGER.debug('Sending images to host {}'.format(host.name))
            for image in project_images:
                LOGGER.debug('Sending image {} to host {}'
                             ''.format(image, host.name))
                copy_image(image, config.image_builder, host)


def delete_all_images():
    LOGGER.info('Deleting all the images of the current project')
    for host in config.hosts:
        LOGGER.debug('Connecting to host {}'.format(host.name))
        host_client = host.get_docker_client()

        for queue in config.queues:
            LOGGER.debug('Deleting worker image for queue {} on host {}'
                         ''.format(queue.name, host.name))
            try:
                delete_worker_image_for_queue(queue.name, host_client)
            except ImageNotFound:
                LOGGER.debug('Queue {} has no worker image on host {}. No '
                             'attempt to delete it will be performed'
                             ''.format(queue.name, host.name))

            LOGGER.debug('Deleting job submiter image for queue {} on host {}'
                         ''.format(queue.name, host.name))
            try:
                delete_job_submitter_image_for_queue(queue.name, host_client)
            except ImageNotFound:
                LOGGER.debug('Queue {} has no job submitter image on host {}. '
                             'No attempt to delete it will be performed'
                             ''.format(queue.name, host.name))

        LOGGER.debug('Deleting slurm master image on host {}'
                     ''.format(host.name))
        try:
            delete_slurm_master_image(host_client)
        except ImageNotFound:
            LOGGER.debug('Slurm master image not found on host {}! It will not '
                         'be removed'.format(host.name))

        LOGGER.debug('Deleting linker image on host {}'
                     ''.format(host.name))
        try:
            delete_linker_image(host_client)
        except ImageNotFound:
            LOGGER.debug('Linker image not found on host {}! It will not be '
                         'removed'.format(host.name))

    LOGGER.info('All images deleted')
