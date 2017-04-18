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
The console interface allows to manage Dockerhood from a command line.
"""

from threading import Thread
from time import sleep
from sys import exit, stderr, stdin
from os import isatty
import logging
import readline

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.template_render import template_render
from dockerhood_libraries.docker_utilities import test_hosts
from dockerhood_libraries.image_handlers import *
from dockerhood_libraries.container_handlers import *

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)

class HistorySaver(object):
    """
    This object is useful when the software must disable the history of the
    command line (for example, when a question outside the command line is
    asked). This objects saves the entries of the history in a list
    and then empties the history. In such a way, it looks like the history
    feature has been disabled. After that, it is possible to re-enable the
    history copying all the saved elements inside the history
    """
    def __init__(self):
        self._history_elements = []

    def save_history(self):
        self._history_elements = []
        for i in range(readline.get_current_history_length()+1):
            if i is not None:
                self._history_elements.append(readline.get_history_item(i))
        readline.clear_history()

    def restore_history(self):
        readline.clear_history()
        for i in self._history_elements:
            if i is not None:
                readline.add_history(i)

# This is the HistorySaver that I will use inside this module
rl_history_saver = HistorySaver()


class Completator(object):
    """
    This object completes the current command line typed by the user
    suggesting some valid alternatives that have a valid syntax

    - *status*: A DockerhoodStatus object that reports the current status of
      the software
    """
    ACTIONS = ['create', 'start', 'stop', 'delete', 'report', 'test',
               'rebuild', 'exit']

    def __init__(self, status):
        # These are the possible ends for the current command
        self.matches = []
        self._status = status

        # Initialize the library to get the cursor position
        from ctypes import cdll
        from ctypes.util import find_library
        self.__readline_library = cdll.LoadLibrary(find_library('readline'))

    def get_cursor_position(self):
        from ctypes import c_int
        return int(c_int.in_dll(self.__readline_library, 'rl_point').value)

    def build_matches(self, text):
        current_line = readline.get_line_buffer()[:self.get_cursor_position()]
        text_words = current_line.split()
        if len(current_line) > 0 and current_line[-1] == ' ':
            text_words.append('')

        if len(text_words) <= 1:
            self.matches = [act for act in Completator.ACTIONS
                                if act.startswith(text)]

        elif len(text_words) == 2 and text_words[0] == 'create':
            obj = [
                'keys', 'images', 'linker', 'slurm_master', 'worker',
                'job_submitter'
            ]
            if config.base_image_is_a_template:
                obj.append('base_image')
            self.matches = [act for act in obj if act.startswith(text_words[1])]

        elif len(text_words) == 2 and text_words[0] == 'report':
            obj = [
                'images', 'containers', 'hosts', 'linker', 'keys',
                'slurm_master', 'workers'
            ]
            self.matches = [act for act in obj if act.startswith(text_words[1])]

        elif len(text_words) == 2 and text_words[0] == 'test':
            self.matches = [act for act in ('hosts',)
                                if act.startswith(text_words[1])]

        elif len(text_words) == 2 and text_words[0] == 'rebuild':
            self.matches = [act for act in ('system',)
                                if act.startswith(text_words[1])]

        elif len(text_words) == 2 and \
                        text_words[0] in ('start', 'stop', 'delete'):
            valid_options = [w['ext name'] for w in self._status.worker_list]
            valid_options.append('linker')
            valid_options.append('slurm_master')
            valid_options.append('workers')
            valid_options.append('job_submitter')
            if text_words[0] == 'delete':
                valid_options.append('images')
                if config.base_image_is_a_template:
                    valid_options.append('base_image')
            self.matches = [act for act in valid_options
                                if act.startswith(text_words[1])]

        elif text_words[0] == 'rebuild' and text_words[1] == 'system':
            if config.base_image_is_a_template:
                if len(text_words) == 3:
                    if 'and'.startswith(text_words[2]):
                        self.matches = ['and base_image']
                    else:
                        self.matches = []
                elif len(text_words) == 4:
                    if text_words[3] == 'and' and \
                            'base_image'.startswith(text_words[3]):
                        self.matches == ['base_image']
                    else:
                        self.matches = []
                else:
                    self.matches = []
            else:
                self.matches = []

        elif len(text_words) > 2 and text_words[-2] == 'on':
            self.matches = [host.name for host in config.hosts
                                if host.name.startswith(text_words[-1])]

        elif len(text_words) > 2 and text_words[-2] == 'for':
            self.matches = [queue.name for queue in config.queues
                                if queue.name.startswith(text_words[-1])]

        elif len(text_words) > 2:
            self.matches = [cmd for cmd in ('on', 'for')
                                if cmd.startswith(text_words[-1])]

        else:
            self.matches = []


    def complete(self, text, state):
        if state == 0:
            self.build_matches(text)

        try:
            return self.matches[state]
        except IndexError:
            return None


class ConsoleInterface(Thread):
    def __init__(self, request_handler, status, stop_execution):
        super(ConsoleInterface, self).__init__()
        self._request_handler = request_handler
        self._status = status
        self._stop_execution = stop_execution
        self.daemon = True
        completator = Completator(self._status)
        self._tty_completator = completator.complete

        # Check if standard input is a terminal
        self.uses_tty = isatty(stdin.fileno())

    def run(self):
        # Initialize the command line options
        if self.uses_tty:
            readline.set_completer_delims(' ,\n')
            readline.parse_and_bind("tab: complete")
            readline.set_completer(self._tty_completator)
            cursor_start = '-->> '
            print('Welcome to the Dockerhood command line interface.')
        else:
            cursor_start = ''

        while True:
            # If the execution is stopped, do not execute the received command
            # and do not call "input" anymore. This is important because the
            # input function turns off the terminal echo which the main thread
            # should have reactivated before exiting
            if self._stop_execution:
                break

            try:
                cmd = input(cursor_start)
            except EOFError:
                # This means that the user has close the standard input.
                # We will exit from this interface with a warning message
                LOGGER.info('The command line interface has been stopped')
                print('End of file reached in the standard input file of '
                      'this application. This means that the console '
                      'interface is no longer available. If you want to '
                      'terminate this application, please press Ctrl+C '
                      '(or use another interface)',
                      file=stderr)
                break

            self.parse_and_execute(cmd)

    def _warn_ignored_command(self, cmd):
        """
        Tell to the user that a specific command is ignored. This is useful
        just if the standard input is a file because, otherwise, the user
        know what command he or she has just submitted

        Args:
            - *cmd* (str): a command read from the standard input
        """
        if not self.uses_tty:
            print('WARNING: Ignoring command: "{}"'
                  ''.format(cmd))

    def _warn_error_executing_command(self, cmd):
        """
        Tell to the user which command raised an error. This is useful
        just if the standard input is a file because, otherwise, the user
        know what command he or she has just submitted

        Args:
            - *cmd* (str): a command read from the standard input
        """
        if not self.uses_tty:
            print('WARNING: Error executing: "{}"'
                  ''.format(cmd))

    def _read_options(self, option_list):
        """
        Given a list of words read from the command line, this function
        read the options (like the word that follows the word "on" or
        "for") and put them in a dictionary

        Args:
            - option_list: a list of strings

        Return:
            A dictionary with three values:
                - "host" is the word after "on" (None if no one found)
                - "queue" is the word after "for" (None if no one found)
                - "others" is a list with all the other options
        """
        options = {
            'host' : None,
            'queue' : None,
            'others' : []
        }

        for i in range(1, len(option_list)):
            if option_list[i-1] == 'on':
                options['host'] = option_list[i].lower()
                option_list[i-1] = None
                option_list[i] = None
            if option_list[i-1] == 'for':
                options['queue'] = option_list[i].lower()
                option_list[i-1] = None
                option_list[i] = None

        options['others'] = [opt for opt in option_list if opt is not None]

        return options

    def _ask_for_request(self, action, original_cmd):
        """
        Create a request for a particular action, wait until the request
        has been executed, and report the result

        Args:
            - *action*: a callable object that will be executed by the main
              thread
            - *original_cmd* (str): the original command read from the
              standard input

        Returns:
            a tuple of two elements: the first one is the status of the
            request, the other one is None if the status is ERROR or the
            return value of the action if the status is EXECUTED
        """
        request_uuid = self._request_handler.create_request(action)
        if self.uses_tty:
            print('Action submitted as request {}. Waiting for its execution'
                  ''.format(request_uuid))

        # Sleep until the request is executed
        while self._request_handler.get_request_status(request_uuid)==1:
            sleep(0.1)

        if self.uses_tty:
            print('Request {} is being executed'.format(request_uuid))

        while self._request_handler.get_request_status(request_uuid) == 2:
            sleep(0.1)

        answer = self._request_handler.get_answer(request_uuid)

        if self._request_handler.get_request_status(request_uuid) == -1:
            self._warn_error_executing_command(original_cmd)
            print('Error executing the request: {}'.format(answer))
            return -1, None
        else:
            if self.uses_tty:
                print('Request {} executed!'.format(request_uuid))
            return 3, self._request_handler.get_answer(request_uuid)

    def parse_and_execute(self, cmd_string):
        """
        Given a command as a string, perform the requested operation.

        Args:
            - *cmd_string*: a string that represent a command
        """
        cmd_string_clean = cmd_string.lower().strip()

        # Ignore empty lines
        if cmd_string_clean == '':
            return None

        action = cmd_string_clean.split()[0]

        if action == 'exit':
            if cmd_string_clean != 'exit':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: exit does not accept any other '
                      'arguments!'.format(cmd_string[5:]))
            else:
                self.stop_execution()

        elif action == 'create':
            if cmd_string_clean == 'create':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: missing object for action "create"!')
            else:
                self.create(cmd_string_clean.split()[1:], cmd_string)

        elif action == 'start':
            if cmd_string_clean == 'start':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: missing object for action "start"!')
            else:
                self.start_cmd(cmd_string_clean.split()[1:], cmd_string)

        elif action == 'stop':
            if cmd_string_clean == 'stop':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: missing object for action "stop"!')

            else:
                self.stop_cmd(cmd_string_clean.split()[1:], cmd_string)

        elif action == 'delete':
            if cmd_string_clean == 'delete':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: missing object for action "delete"!')
            else:
                self.delete(cmd_string_clean.split()[1:], cmd_string)

        elif action == 'report':
            if cmd_string_clean == 'report':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: missing object for action "report"!')
            else:
                self.report(cmd_string_clean.split()[1:], cmd_string)

        elif action == 'test':
            if cmd_string_clean[4:].strip() != 'hosts':
                self._warn_ignored_command(cmd_string)
                print('Invalid command: the only allowed object with action '
                      '"test" is "hosts"!')
            else:
                self.test_hosts(cmd_string)

        elif action == 'rebuild':
            words = cmd_string_clean.split()
            if len(words) == 1:
                self._warn_ignored_command(cmd_string)
                print('Invalid command: no object for action "rebuild"')
            elif words[1] != 'system':
                self._warn_ignored_command(cmd_string)
                if config.base_image_is_a_template:
                    print(
                        'Invalid command: the only allowed objects for action '
                        '"rebuild" are "system" and "system and base_image", '
                        'not "{}"!'.format(words[1])
                    )
                else:
                    print(
                        'Invalid command: the only allowed object for action '
                        '"rebuild" is "system", not "{}"!'.format(words[1])
                    )
            elif len(words) >2 and ' '.join(words[2:]) != 'and base_image':
                self._warn_ignored_command(cmd_string)
                print(
                    'Invalid command: no options are allowed for "rebuild '
                    'system" (received "{}")!'.format(' '.join(words[2:]))
                )
            elif ' '.join(words[:]) == 'rebuild system and base_image':
                if config.base_image_is_a_template:
                    answ = 'y'
                    if self.uses_tty:
                        print('******  WARNING  ******')
                        print('This will stop all the containers, delete them, '
                              'delete their images and rebuild everything from '
                              'scratch (please, ensure to have some keys ready '
                              'for the images). Moreover, also the base image '
                              'will be rebuilt!'
                              )
                        rl_history_saver.save_history()
                        answ = input('Are you sure that you want this (y/N)? ')
                        while answ.strip().lower() not in ('y', 'n', ''):
                            readline.clear_history()
                            answ = input('Please, write y or n: ')
                        rl_history_saver.restore_history()
                    if answ == 'y':
                        self.rebuild_system_and_base_image(cmd_string)
                else:
                    self._warn_ignored_command(cmd_string)
                    print(
                        'Invalid command: rebuild base image is a valid option '
                        'only if the image has been generated from a template'
                    )
            elif ' '.join(words[:]) == 'rebuild system':
                answ = 'y'
                if self.uses_tty:
                    print('******  WARNING  ******')
                    print('This will stop all the containers, delete them, '
                          'delete their images and rebuild everything from '
                          'scratch (please, ensure to have some keys ready '
                          'for the images).')
                    rl_history_saver.save_history()
                    answ = input('Are you sure that you want this (y/N)? ')
                    while answ.strip().lower() not in ('y', 'n', ''):
                        readline.clear_history()
                        answ = input('Please, write y or n: ')
                    rl_history_saver.restore_history()
                if answ == 'y':
                    self.rebuild_system(cmd_string)
        else:
            self._warn_ignored_command(cmd_string)
            print('Invalid action: "{}"!'.format(action))

    def stop_execution(self):
        """
        This is the command that the console uses to stop the system.
        It sends a request to stop the software to the main thread
        """
        print('The execution will stop as soon as all the pending operations '
              'will be completed')
        request_uuid = self._request_handler.create_request(exit)

        # Sleep so that the user can not submit other commands while waiting
        # for exit
        while self._request_handler.get_request_status(request_uuid) in (1, 2):
            sleep(0.1)

        if self._request_handler.get_request_status(request_uuid) == -1:
            print('Request failed! Exit command not executed!')
        else:
            exit(0)

    def create(self, options, original_cmd):
        """
        Execute a command that starts with the action "create"

        Args:
            - *options*: a list where the first element is the object to be
              created and the other are the options that depend on the kind
              of the object
            - *original_cmd* (str): the original comand submitted to the
              command line
        """
        object = options[0]

        if object == 'keys':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: create keys does not accept any '
                      'options')
            else:
                def action():
                    return create_keys()
                self._ask_for_request(action, original_cmd)
        elif object == 'images':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: create images does not accept any '
                      'options')
            else:
                def action():
                    return create_all_images()
                self._ask_for_request(action, original_cmd)
        elif object == 'base_image':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: create images does not accept any '
                      'options')
            else:
                def action():
                    build_clt = config.image_builder.get_docker_client()
                    return create_base_image(build_clt)
                self._ask_for_request(action, original_cmd)
        elif object == 'linker':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: create linker does not accept any '
                      'options')
            else:
                def action():
                    return start_linker()
                self._ask_for_request(action, original_cmd)
        elif object == 'slurm_master':
            options = self._read_options(options[1:])
            if options['host'] is None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: missing host. Specify the host with '
                      ' the following syntax: "create slurm_master on '
                      'HOSTNAME"')
            elif options['host'] not in [h.name for h in config.hosts]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: host {} does not exist'
                      ''.format(options['host']))
            elif options['queue'] is not None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "create slurm_master" does not require '
                      'to specify a queue (do not use the "for QUEUE" syntax)')
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    return start_slurm_master(options['host'])
                self._ask_for_request(action, original_cmd)
        elif object == 'job_submitter':
            options = self._read_options(options[1:])
            if options['host'] is None:
                self._warn_ignored_command(original_cmd)
                print(
                    'Invalid command: missing host. Specify the host with '
                    ' the following syntax: "create job_submitter on '
                    'HOSTNAME for QUEUENAME"')
            elif options['host'] not in [h.name for h in config.hosts]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: host {} does not exist'
                      ''.format(options['host']))
            elif options['queue'] is None:
                self._warn_ignored_command(original_cmd)
                print(
                    'Invalid command: missing queue. Specify the queue with '
                    ' the following syntax: "create job submitter on '
                    'HOSTNAME for QUEUENAME"')
            elif options['queue'] not in [q.name for q in config.queues]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: queue {} does not exist'
                      ''.format(options['queue']))
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    js_host = job_submitter_host_for_queue(options['queue'])
                    if js_host is not None:
                        raise Exception('A job submitter container for queue '
                                        '{} has already been created'
                                        ''.format(options['queue']))
                    return start_job_submitter(options['queue'],
                                               options['host'])
                self._ask_for_request(action, original_cmd)
        elif object == 'worker':
            options = self._read_options(options[1:])
            if options['host'] is None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: missing host. Specify the host with '
                      'the following syntax: "create slurm_master on '
                      'HOSTNAME for QUEUE"')
            elif options['host'] not in [h.name for h in config.hosts]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: host {} does not exist'
                      ''.format(options['host']))
            elif options['queue'] is None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: missing queue. Specify the queue '
                      'with the following syntax: "create slurm_master on '
                      'HOSTNAME for QUEUE"')
            elif options['queue'] not in [q.name for q in config.queues]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: queue {} does not exist'
                      ''.format(options['queue']))
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    return create_worker(
                                         options['queue'],
                                         options['host'],
                                         )
                status, cont_name = self._ask_for_request(action, original_cmd)
                print('Created new container named {}'.format(cont_name))
        else:
            self._warn_ignored_command(original_cmd)
            print('Invalid object! {} is not a valid object for the '
                  'action "create"'.format(object))

    def start_cmd(self, options, original_cmd):
        """
        Execute a command that starts with the action "start"

        Args:
            - *options*: a list where the first element is the object to be
              created and the other are the options that depend on the kind
              of the object
            - *original_cmd* (str): the original comand submitted to the
              command line
        """
        object = options[0]

        if object == 'linker':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "start linker" does not accept any '
                      'options')
            else:
                def action():
                    return start_linker()
                self._ask_for_request(action, original_cmd)
        elif object == 'slurm_master':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "start slurm_master" does not accept '
                      'any options')
            else:
                def action():
                    sl_host = slurm_master_host()
                    if sl_host is None:
                        raise Exception('No slurm master container found')
                    return start_slurm_master(sl_host.name)
                self._ask_for_request(action, original_cmd)
        elif object == 'workers':
            options = self._read_options(options[1:])
            host_names = [h.name for h in config.hosts]
            queue_names = [q.name for q in config.queues]
            if options['host'] is not None and options['host'] not in host_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Host {} does not exist'
                      ''.format(options['host']))
                return
            if options['queue'] is not None and options['queue'] not in queue_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Queue {} does not exist'
                      ''.format(options['queue']))
                return
            if len(options['others']) != 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
                return

            queue = options['queue']
            host = options['host']

            def action():
                workers = [w for w in self._status.worker_list
                               if queue is None or w['queue'] == queue
                               if host is None or w['host'].name == host]
                for worker in workers:
                    try:
                        start_worker(worker['ext name'])
                    except WorkerAlreadyStarted:
                        pass
            self._ask_for_request(action, original_cmd)
        elif object == 'job_submitter':
            options = self._read_options(options[1:])
            if options['queue'] is None:
                self._warn_ignored_command(original_cmd)
                print(
                    'Invalid command: missing queue. Specify the queue with '
                    ' the following syntax: "start job_submitter for '
                    'QUEUENAME"')
            elif options['queue'] not in [q.name for q in config.queues]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: queue {} does not exist'
                      ''.format(options['queue']))
            elif options['host'] is not None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "start job_submitter" does not require '
                      'to specify an host')
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    js_host = job_submitter_host_for_queue(options['queue'])
                    if js_host is None:
                        raise Exception('No job submitter container found for '
                                        'queue {}'.format(options['queue']))
                    return start_job_submitter(options['queue'], js_host.name)
                self._ask_for_request(action, original_cmd)
        else:
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command! No options are allowed! '
                      'Use "start CONTAINER"')
            else:
                def action():
                    return start_worker(options[0])
                self._ask_for_request(action, original_cmd)

    def stop_cmd(self, options, original_cmd):
        """
        Execute a command that starts with the action "stop"

        Args:
            - *options*: a list where the first element is the object to be
              stopped and the other are the options that depend on the kind
              of the object
            - *original_cmd* (str): the original comand submitted to the
              command line
        """
        object = options[0]

        if object == 'linker':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "stop linker" does not accept any '
                      'options')
            else:
                def action():
                    return stop_linker()
                self._ask_for_request(action, original_cmd)
        elif object == 'slurm_master':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "stop slurm_master" does not accept '
                      'any options')
            else:
                def action():
                    return stop_slurm_master()
                self._ask_for_request(action, original_cmd)
        elif object == 'workers':
            options = self._read_options(options[1:])
            host_names = [h.name for h in config.hosts]
            queue_names = [q.name for q in config.queues]
            if options['host'] is not None and options['host'] not in host_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Host {} does not exist'
                      ''.format(options['host']))
                return
            if options['queue'] is not None and options['queue'] not in queue_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Queue {} does not exist'
                      ''.format(options['queue']))
                return
            if len(options['others']) != 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
                return

            queue = options['queue']
            host = options['host']

            def action():
                workers = [w for w in self._status.worker_list
                               if queue is None or w['queue'] == queue
                               if host is None or w['host'].name == host]
                for worker in workers:
                    try:
                        stop_worker(worker['ext name'])
                    except WorkerAlreadyStopped:
                        pass
            self._ask_for_request(action, original_cmd)
        elif object == 'job_submitter':
            options = self._read_options(options[1:])
            if options['queue'] is None:
                self._warn_ignored_command(original_cmd)
                print(
                    'Invalid command: missing queue. Specify the queue with '
                    ' the following syntax: "stop job_submitter for QUEUENAME"')
            elif options['queue'] not in [q.name for q in config.queues]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: queue {} does not exist'
                      ''.format(options['queue']))
            elif options['host'] is not None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "stop job_submitter" does not require '
                      'to specify an host (do NOT use the "on HOST" syntax)')
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    return stop_job_submitter_for_queue(options['queue'])
                self._ask_for_request(action, original_cmd)
        else:
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command! No options are allowed! '
                      'Use "stop CONTAINER"')
            else:
                def action():
                    return stop_worker(options[0])
                self._ask_for_request(action, original_cmd)

    def delete(self, options, original_cmd):
        """
        Execute a command that starts with the action "delete"

        Args:
            - *options*: a list where the first element is the object to be
              deleted and the other are the options that depend on the kind
              of the object
            - *original_cmd* (str): the original comand submitted to the
              command line
        """
        object = options[0]

        if object == 'linker':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "delete linker" does not accept any '
                      'options')
            else:
                def action():
                    return delete_linker()
                self._ask_for_request(action, original_cmd)
        elif object == 'slurm_master':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "delete slurm_master" does not accept '
                      'any options')
            else:
                def action():
                    return delete_slurm_master()
                self._ask_for_request(action, original_cmd)
        elif object == 'base_image':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "delete base_image" does not accept '
                      'any options')
            else:
                def action():
                    build_clt = config.image_builder.get_docker_client()
                    return delete_base_image(build_clt)
                self._ask_for_request(action, original_cmd)
        elif object == 'images':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "delete images" does not accept '
                      'any options')
            else:
                def action():
                    return delete_all_images()
                self._ask_for_request(action, original_cmd)
        elif object == 'workers':
            options = self._read_options(options[1:])
            host_names = [h.name for h in config.hosts]
            queue_names = [q.name for q in config.queues]
            if options['host'] is not None \
                    and options['host'] not in host_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Host {} does not exist'
                      ''.format(options['host']))
                return
            if options['queue'] is not None \
                    and options['queue'] not in queue_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Queue {} does not exist'
                      ''.format(options['queue']))
                return
            if len(options['others']) != 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
                return

            queue = options['queue']
            host = options['host']

            def action():
                workers = [w for w in self._status.worker_list
                               if queue is None or w['queue'] == queue
                               if host is None or w['host'].name == host]
                for worker in workers:
                    delete_worker(worker['ext name'])

            self._ask_for_request(action, original_cmd)
        elif object == 'job_submitter':
            options = self._read_options(options[1:])
            if options['queue'] is None:
                self._warn_ignored_command(original_cmd)
                print(
                    'Invalid command: missing queue. Specify the queue with '
                    ' the following syntax: "delete job_submitter for '
                    'QUEUENAME"')
            elif options['queue'] not in [q.name for q in config.queues]:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: queue {} does not exist'
                      ''.format(options['queue']))
            elif options['host'] is not None:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "delete job_submitter" does not require'
                      ' to specify an host (do NOT use the "on HOST" syntax)')
            elif len(options['others']) > 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
            else:
                def action():
                    return delete_job_submitter_for_queue(options['queue'])
                self._ask_for_request(action, original_cmd)
        else:
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command! No options are allowed! '
                      'Use "delete CONTAINER"')
            else:
                def action():
                    return delete_worker(options[0])
                self._ask_for_request(action, original_cmd)

    def report(self, options, original_cmd):
        """
        Execute a command that starts with the action "report"

        Args:
            - *options*: a list where the first element is the object to
              describe and the other are the options that depend on the kind
              of the object
            - *original_cmd* (str): the original comand submitted to the
              command line
        """
        object = options[0]

        if object == 'images':
            if len(options) == 1:
                for host in config.hosts:
                    print('- Images found on host {}'.format(host.name))
                    for image in self._status.images[host]:
                        print('  * {}'.format(image))
            elif options[1] != 'on':
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid option {}'.format(options[1]))
            elif len(options) == 2:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: missing host after "on"')
            elif len(options) > 3:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: too many options. Use "report '
                      'images on HOSTNAME"')
            else:
                host_name = options[2]
                valid_hosts = [h for h in config.hosts
                                       if h.name == host_name]
                if len(valid_hosts) == 0:
                    self._warn_ignored_command(original_cmd)
                    print('No valid host found named {}'.format(host_name))
                    return

                host = valid_hosts[0]
                img_list = self._status.images[host]
                if len(img_list) == 0:
                    print('No image found on host {}'.format(host.name))
                    return

                print('These are the images found on host {}:'
                      ''.format(host.name))
                for img in img_list:
                    print('  * {}'.format(img))

        elif object == 'containers':
            print('LINKER\n' + '-'*30)
            self.report(['linker'], original_cmd)

            print('\nSLURM MASTER\n' + '-'*30)
            self.report(['slurm_master'], original_cmd)

            print('\nWORKERS\n' + '-'*30)
            self.report(['workers'], original_cmd)

        elif object == 'keys':
            if check_keys():
                print('The VPN keys have been generated')
            else:
                print('The VPN keys have NOT been generated')

        elif object == 'linker':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "report linker" does not accept any '
                      'options')
            else:
                if self._status.linker_is_running:
                    print('Linker container is running')
                elif self._status.linker_exists:
                    print('Linker container is stopped')
                else:
                    print('No linker container on the system')

        elif object == 'slurm_master':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "report slurm_master" does not accept '
                      'any options')
            else:
                if self._status.slurm_master_host is None:
                    mssg = 'No slurm master container found'
                else:
                    mssg = 'Linker container exists on host {}'\
                           ''.format(self._status.slurm_master_host.name)
                    if self._status.slurm_master_is_running is True:
                        mssg += ' and is running!'
                    else:
                        mssg += ', but is stopped!'
                print(mssg)

        elif object == 'workers':
            options = self._read_options(options[1:])
            host_names = [h.name for h in config.hosts]
            queue_names = [q.name for q in config.queues]
            if options['host'] is not None and options['host'] not in host_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Host {} does not exist'
                      ''.format(options['host']))
                return
            if options['queue'] is not None and options['queue'] not in queue_names:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: Queue {} does not exist'
                      ''.format(options['queue']))
                return
            if len(options['others']) != 0:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: invalid options submitted ({})'
                      ''.format(', '.join(options['others'])))
                return

            queue = options['queue']
            host = options['host']

            wrks_in_queue = [w for w in self._status.worker_list
                                  if queue is None or w['queue'] == queue]
            if host is not None:
                workers = [w for w in wrks_in_queue if w['host'].name == host]
                if len(workers) == 0:
                    message = 'No workers on host {}'.format(host)
                    if queue is not None:
                        message += ' for queue {}'.format(queue)
                    print(message)
                else:
                    print('Workers on host {}'.format(host), end = '')
                    if queue is not None:
                        print(' for queue {}:'.format(queue))
                    else:
                        print(':')
                    for worker in workers:
                        print('  -  {}'.format(worker['ext name']))
                return
            hosts_without_containers = []
            for host in (h.name for h in config.hosts):
                workers = [w for w in wrks_in_queue if w['host'].name == host]
                if len(workers) == 0:
                    hosts_without_containers.append(host)
                else:
                    print('Workers on host {}'.format(host), end='')
                    if queue is not None:
                        print(' for queue {}:'.format(queue))
                    else:
                        print(':')
                    for worker in workers:
                        if worker['active']:
                            print('  -  {} (running)'.format(worker['ext name']))
                        else:
                            print('  -  {} (stopped)'.format(worker['ext name']))
            if len(hosts_without_containers) > 0:
                print('No workers on the following hosts: {}'
                      ''.format(', '.join(hosts_without_containers)))

        elif object == 'hosts':
            if len(options) > 1:
                self._warn_ignored_command(original_cmd)
                print('Invalid command: "report hosts" does not accept any '
                      'options')
            else:
                print('Dockerhood is running on the following hosts:')
                for host in config.hosts:
                    if host.ip is None:
                        print('  * {}'.format(host))
                    else:
                        print('  * {} on ip {}'.format(host, host.ip))

        else:
            self._warn_ignored_command(original_cmd)
            print('Invalid object! {} is not a valid object for the '
                  'action "report"'.format(object))

    def test_hosts(self, original_cmd):
        def test():
            return test_hosts()
        req_status, test_result = self._ask_for_request(test, original_cmd)
        if req_status > 0:
            for host, test_answer in test_result.items():
                print('Answer from host {}'.format(host.name))
                print('-' * 60)
                print(test_answer)

    def rebuild_system(self, original_cmd):
        def action():
            delete_all_containers()
            delete_all_images()
            create_all_images()

        self._ask_for_request(action, original_cmd)

    def rebuild_system_and_base_image(self, original_cmd):
        def action():
            delete_all_containers()
            delete_all_images()
            build_clt = config.image_builder.get_docker_client()
            try:
                delete_base_image(build_clt)
            except BaseImageNotBuilt:
                pass
            create_all_images()

        self._ask_for_request(action, original_cmd)
