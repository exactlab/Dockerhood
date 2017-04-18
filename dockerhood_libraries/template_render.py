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

from os import getuid, getgid, path, listdir, mkdir
from shutil import copy, rmtree
import re
import logging

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.docker_utilities import StreamLine

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"


INSERT_COMMAND = \
    r"^ *{% ?insert '(?P<in_file>.*?)' in '(?P<docker_file>.*?)' ?%} *$"
INSERT_SYNTAX = re.compile(INSERT_COMMAND, re.MULTILINE)

FOR_COMMAND = \
    r'^ *{% *for *(?P<indx>[^ ]*) +in +(?P<fld>[^ ]*) *%} *$'
END_FOR_COMMAND = r'^ *{% *end_for *%} *$'
FOR_SYNTAX = re.compile(FOR_COMMAND, re.MULTILINE)
END_FOR_SYNTAX = re.compile(END_FOR_COMMAND, re.MULTILINE)

LOGGER = logging.getLogger(__name__)


def bash_sanitize(line):
    line = line.replace("'", "'\\''")
    return line


class TemplateRender(object):
    """
    A TemplateRender is an object that uses some templates of a Dockerfile to
    generate a docker image.

    The difference between a real Dockerfile and a Dockerfile template is that
    the templates contains values that must be substituted by a TemplateRender
    object. For example:

      * the uid and gid of the user
      * the parameters of the VPNs (ips, ports, etc.)
      * the parameters for the VPN keys defined in the configuration

    Moreover, it is also possible to use a dictionary of values to substitute
    some values inside the template.

    To generate the image, the template render will use a directory as a scratch
    area. *All the files that are inside this directory will be deleted before
    starting the execution of the render!* Therefore, it is wise to use an empty
    directory as stage area or, at least, a directory that does not contain
    important files.

    Args:
        - *config*: a configuration object
        - *scratch_dir* (str): the directory that will be used as scratch
        - *key_dir* (str): the directory with all the keys for the VPNs
    """
    def render(self, system_template, user_template, image_name, docker_cli,
               subst_dict=None):
        """
        Transform a template into a docker image

        Args:
            - *system_template* (str): the name of the system template
            - *user_template* (str): the name of the user template
            - *image_name* (str): the name of the image generated as output
            - *docker_cli*: a docker command line interface (generated by
              the docker-py library)
            - *subst_dict* (str, optional): A dictionary of values that will be
              substituted inside the Dockerfile. By default is empty.
        """
        if system_template is None and user_template is None:
            raise ValueError(
                'System template and user template can not be both "None"'
            )

        # This is the content of the template (both system and user template)
        docker_template = ''

        # Read the system dockerfile template
        if system_template is not None:
            system_template_path = path.join(config.template_dir,
                                             system_template + '.template')
            LOGGER.debug('Checking if {} exists'.format(system_template_path))
            if not path.isdir(system_template_path):
                raise IOError('Directory {} not found (needed for template {})'
                              ''.format(system_template_path, system_template))

            system_dockerfile_path = path.join(system_template_path,
                                               'Dockerfile')
            with open(system_dockerfile_path, 'r') as f:
                system_dockerfile = f.read()
            docker_template += system_dockerfile

        # Read the user dockerfile template
        if user_template is not None:
            user_template_path = path.join(config.user_template_dir,
                                           user_template + '.template')
            LOGGER.debug('Checking if {} exists'.format(user_template_path))
            if not path.isdir(user_template_path):
                raise IOError('Directory {} not found (needed for template {})'
                              ''.format(user_template_path, user_template))

            user_dockerfile_path = path.join(user_template_path,
                                             'Dockerfile')
            with open(user_dockerfile_path, 'r') as f:
                user_dockerfile = f.read()

            # Ensure that no FROM command is submitted in the user template
            # The FROM command is valid only if we are not starting from a
            # system template
            if system_template is not None:
                user_dockerfile_lines = user_dockerfile.split('\n')
                user_dockerfile_compact_lines = []
                append_next = False
                for line in user_dockerfile_lines:
                    if not append_next:
                        user_dockerfile_compact_lines.append(line.strip())
                    else:
                        user_dockerfile_compact_lines[-1] += line.strip()
                    append_next = False
                    if line.strip().endswith("\\"):
                        append_next = True
                        # Remove the \ at the end of the line
                        user_dockerfile_compact_lines[-1] = \
                            user_dockerfile_compact_lines[-1][:-1]

                for line_num, line in enumerate(user_dockerfile_compact_lines):
                    if line.upper().startswith('FROM'):
                        raise ValueError(
                            'FROM command not allowed in user templates! Error '
                            'in line {} of template {} ({})'
                            .format(line_num + 1, user_template, line)
                        )

            docker_template += user_dockerfile

        # Clean the scratch area
        LOGGER.debug('Removing the directory {}'.format(config.scratch_dir))
        rmtree(config.scratch_dir)
        LOGGER.debug('Creating empty directory {}'.format(config.scratch_dir))
        mkdir(config.scratch_dir)

        # Move every file that is in the key dir to the scratch area
        for fl in listdir(config.keys_dir):
            LOGGER.debug('Copying file {} from {} to the scratch area {}'
                         ''.format(fl, config.keys_dir, config.scratch_dir))
            old_file = path.join(config.keys_dir, fl)
            new_file = path.join(config.scratch_dir, fl)
            copy(old_file, new_file)

        # Move every file in the system template dir (beside the Dockerfile)
        # to the scratch area
        if system_template is not None:
            for fl in listdir(system_template_path):
                if fl != 'Dockerfile':
                    LOGGER.debug('Copying file {} from {} to the scratch area '
                                 '{}'.format(fl,
                                             system_template_path,
                                             config.scratch_dir
                                             )
                                 )
                    old_file = path.join(system_template_path, fl)
                    new_file = path.join(config.scratch_dir, fl)
                    copy(old_file, new_file)

        # Move every file in the user template dir (beside the Dockerfile)
        # to the scratch area
        if user_template is not None:
            for fl in listdir(user_template_path):
                if fl != 'Dockerfile':
                    LOGGER.debug(
                        'Copying file {} from {} to the scratch area {}'
                        ''.format(fl,
                                  user_template_path,
                                  config.scratch_dir
                                  )
                        )
                    old_file = path.join(user_template_path, fl)
                    new_file = path.join(config.scratch_dir, fl)

                    if path.exists(new_file):
                        LOGGER.warning(
                            'The template {} will overwrite the file {}, '
                            'which is a system file'
                            ''.format(user_template, old_file)
                        )

                    copy(old_file, new_file)

        # Now we will build the docker_file performing some substitutions on the
        # docker_template content
        docker_file = docker_template

        # Execute the insert commands
        for insert_command in INSERT_SYNTAX.finditer(docker_template):
            LOGGER.debug('Found an "insert line": {}'
                         ''.format(insert_command.group(0)))
            insert_content = insert_command.group(1)
            insert_file = insert_command.group(2)

            LOGGER.debug('Opening file {} from the scratch dir {}'
                         ''.format(insert_content, config.scratch_dir))
            with open(path.join(config.scratch_dir, insert_content), 'r') as f:
                insert_lines = f.readlines()

            LOGGER.debug('Putting file {} in the Dockerfile'
                         ''.format(insert_content))
            insert_text = 'RUN '
            for l in insert_lines:
                sanitized_l = bash_sanitize(l)
                insert_text += "/bin/echo '" + sanitized_l[:-1] + \
                               "' >> " + str(insert_file) + ' && \\\n' + \
                               '    '
            insert_text = insert_text[:-10]
            docker_file = docker_file.replace(insert_command.group(0),
                                              insert_text)

        # Execute the for commands
        end_for = END_FOR_SYNTAX.search(docker_file)
        while end_for is not None:
            end_for_position = end_for.start()
            start_for_list = list(re.finditer(FOR_SYNTAX,
                                              docker_file[:end_for_position])
                                  )
            if len(start_for_list) == 0:
                if system_template is None:
                    raise Exception('Unbalanced FOR in {} template'
                                    ''.format(user_template))
                elif user_template is None:
                    raise Exception('Unbalanced FOR in {} template'
                                    ''.format(system_template))
                else:
                    raise Exception('Unbalanced FOR in one of the following '
                                    'templates: {} or {}'
                                    ''.format(system_template, user_template))
            start_for_position = start_for_list[-1].end() + 1

            inside_for = docker_file[start_for_position:end_for_position]
            field = start_for_list[-1].group('fld')
            index = start_for_list[-1].group('indx')

            if field == 'queues':
                for_replacement = ''
                for q in config.queues:
                    # Prepare the field "fixed_ip" which is the fixed part of
                    # the ip of the network (the first three numbers)
                    network_ip_string = q.network_ip.as_string()
                    fixed_ip = '.'.join(network_ip_string.split('.')[:-1])

                    # Create a function that, given the name of a field,
                    # prepares the tag of that field in the file, so for
                    # example, for the field "name", it returns {{index.name}}
                    def field(field_name):
                        return '{{' + index + '.' + field_name + '}}'

                    current_text = inside_for
                    current_text = current_text.replace(
                                                        field('name'),
                                                        q.name
                                                        )
                    current_text = current_text.replace(
                                                        field('port'),
                                                        str(q.port)
                                                        )
                    current_text = current_text.replace(
                                                        field('subnet'),
                                                        q.network_ip.as_string()
                                                        )
                    current_text = current_text.replace(
                                                        field('ip_fixed_part'),
                                                        fixed_ip
                                                        )
                    for_replacement += current_text

                docker_file = docker_file[:start_for_list[-1].start()] \
                              + for_replacement \
                              + docker_file[end_for.end() + 1:]

            end_for = END_FOR_SYNTAX.search(docker_file)

        if FOR_SYNTAX.search(docker_file) is not None:
            if system_template is None:
                raise Exception('Unbalanced FOR in {} template'
                                ''.format(user_template))
            elif user_template is None:
                raise Exception('Unbalanced FOR in {} template'
                                ''.format(system_template))
            else:
                raise Exception('Unbalanced FOR in one of the following '
                                'templates: {} or {}'
                                ''.format(system_template, user_template))

        # Substitute the GID and the UID vars
        if getuid() == 0:
            uid = '1000'
            gid = '1000'
        else:
            uid = str(getuid())
            gid = str(getgid())
        docker_file = docker_file.replace('{{UID}}', uid)
        docker_file = docker_file.replace('{{GID}}', gid)

        # Substitute the values of the keys
        for config_field in config.keys['DOCKER KEYS']:
            config_value = config.keys['DOCKER KEYS'][config_field]
            docker_file = docker_file.replace(
                                       '{{' + config_field.upper() + '}}',
                                       config_value
                                       )
        # Substitute the name of the base image
        if config.base_image_is_a_template:
            base_image_name = '{}_base_image'.format(config.project)
        else:
            base_image_name = config.base_image_name
        docker_file = docker_file.replace(
                                          '{{BASE_IMAGE_NAME}}',
                                          base_image_name
                                          )
        # Substitute the IP of the machine with the linker
        docker_file = docker_file.replace(
                                          '{{LINKER_IP}}',
                                          config.linker_ip.as_string()
                                          )

        # Substitute the values of the static network variables
        network_address = config.static_network.network_ip.as_string()
        docker_file = docker_file.replace(
                                          '{{STATIC_NETWORK}}',
                                          network_address,
                                          )

        server_address = config.static_network.server_address.as_string()
        docker_file = docker_file.replace(
                                          '{{STATIC_NETWORK_SERVER_ADDRESS}}',
                                          server_address
                                          )

        port_number = str(config.static_network.port)
        docker_file = docker_file.replace(
                                          '{{STATIC_NETWORK_PORT}}',
                                          port_number
                                          )
        for service in config.static_network.services:
            service_field = '{{' + service.name.upper() + '_IP}}'
            service_ip = service.ip.as_string()
            LOGGER.debug('Replacing {} with {}'
                         ''.format(service_field, service_ip))
            docker_file = docker_file.replace(service_field, service_ip)

        # Substitute the values in the dictionary subst_dict
        if subst_dict is None:
            subst_dict = {}
        for field, value in subst_dict.items():
            docker_file = docker_file.replace(
                                              '{{' + field + '}}',
                                              str(value),
                                              )

        LOGGER.debug('Reporting the rendered Dockerfile: {}'
                     ''.format(docker_file))

        LOGGER.debug('Saving generated dockerfile on {}'
                     ''.format(path.join(config.scratch_dir, 'Dockerfile')))
        with open(path.join(config.scratch_dir, 'Dockerfile'), 'w') as f:
            f.write(docker_file)

        build_exec = docker_cli.build(
                                      path = config.scratch_dir,
                                      tag = image_name,
                                      rm = True,
                                      forcerm = True,
                                      )
        for oper in build_exec:
            stream_line = StreamLine(oper)
            if stream_line.status == 'ERROR':
                raise Exception('Error building image {}: {}'
                                ''.format(image_name, stream_line.message))
            elif stream_line.status == 'UNKONWN':
                LOGGER.warning('Unrecongized docker message: {}'
                               ''.format(stream_line.raw))
            else:
                LOGGER.debug('Docker building: {}'
                             ''.format(stream_line.message))

template_render = TemplateRender()
