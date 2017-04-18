#!/usr/bin/env python3

#
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
Dockerhood

Dockerhood is a free library that allows to "virtualize" a slurm cluster.
It can be used for didactic purposes or for solving embarassing parallel
problems.

:copyright: 2016 by eXact-lab
"""

from os import path, system
import logging
from time import sleep

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.status import DockerhoodStatus, StatusUpdater
from dockerhood_libraries.requests import RequestManager
from dockerhood_interfaces.console import ConsoleInterface

if __name__ == '__main__':
    LOGGER = logging.getLogger()
else:
    LOGGER = logging.getLogger(__name__)

# The BASEDIR is the directory where dockerhood.py is stored
BASEDIR = path.dirname(path.abspath(__file__))
CONFIGDIR = path.join(BASEDIR, 'dockerhood_config')

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"
__credits__ = ["Stefano Piani",]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Stefano Piani"
__email__ = "stefano.piani@exact-lab.it"

class StopExecutionFlag(object):
    """
    A Flag that is raised when the execution of a thread must be stopped
    """
    def __init__(self):
        self.__value = False

    def __bool__(self):
        return self.__value

    def set(self):
        self.__value = True


def configure_logger(config):
    """
    Set the logger to write on the file specified in the configuration
    parameters and with the desired verbosity
    """
    log_verbosity = getattr(logging, config.log_verbosity.upper())
    LOGGER.setLevel(log_verbosity)

    # Create a formatter for the output
    fmt = '%(asctime)s - %(levelname)s - '\
          '%(name)s (%(funcName)s): %(message)s'
    datefmt = '%d/%m/%Y %H:%M:%S'
    formatter = logging.Formatter(fmt, datefmt)

    # Create a handle to write output on the log file
    file_handler = logging.FileHandler(config.log_file)
    file_handler.setLevel(log_verbosity)
    file_handler.setFormatter(formatter)

    # Add the stream handler to the logger
    LOGGER.addHandler(file_handler)


if __name__ == '__main__':
    # Initialize the system populating the object that will store all
    # the configuration parameters of Dockerhood and configuring the logger
    config.read_from_dir(CONFIGDIR, BASEDIR)
    configure_logger(config)

    # Create an object that stores the current status of Dockerhood (like the
    # status of the containers or of the images)
    dockerhood_status = DockerhoodStatus()

    # Create a flag to be raised to stop the threads
    stop_execution = StopExecutionFlag()

    # Create a list of all the threads spawned by the main one
    spawned_threads = []

    # Prepare a function to stop the threads when the execution ends
    # This is not strictly necessary: indeed the other threads are
    # daemons and, therefore, when the main thread will close they
    # will do the same. In any case, if this procedure performs as
    # expected, the main thread will be the last one to stop its
    # execution and, therefore, it is possible to perform some clean-up
    # operations. The only exception is the console interface when the
    # exit request does not come from it. In this case, that thread is
    # blocked on a input command which is non-interruptable. Therefore
    # its thread will be closed because of the fact that it is a daemon
    # when the main thread stops. For this reason, the console interface
    # is not added to the spawned_threads list
    def stop_threads():
        LOGGER.debug('Raising a flag to stop all the threads')
        stop_execution.set()

        for thrd_name, thrd in spawned_threads:
            LOGGER.debug('Waiting for the {} to stop'.format(thrd_name))
            thrd.join(5)
            if thrd.isAlive():
                LOGGER.debug('Timeout reached! The {} is still running'
                             ''.format(thrd_name))
            else:
                LOGGER.debug('{} stopped'.format(thrd_name))
        LOGGER.debug('All threads have been stopped')

    console_interface = None

    try:
        # Start the thread that will update the dockerhood_status object
        LOGGER.debug('Starting the StatusUpdater')
        status_updater = StatusUpdater(dockerhood_status, stop_execution)
        status_updater.start()
        spawned_threads.append(('status updater', status_updater))

        # Start the RequestManager, the thread that will take care of the
        # order and assigns the request performed by the different interfaces
        LOGGER.debug('Starting the RequestManager')
        request_manager = RequestManager(stop_execution)
        request_manager.start()
        spawned_threads.append(('request manager', request_manager))
        LOGGER.debug('Starting the interfaces')
        console_interface = ConsoleInterface(request_manager,
                                             dockerhood_status,
                                             stop_execution,
                                             )
        console_interface.start()

        LOGGER.debug('Starting to execute requests')
        while True:
            request = request_manager.get_next_request()

            if request is None:
                sleep(0.1)
                continue

            LOGGER.debug('Starting to execute request {}'
                         ''.format(request.uuid))
            status_updater.pause()
            request.execute()
            status_updater.update()
            status_updater.unpause()

    except SystemExit:
        LOGGER.info('Stopping execution as requested by request {}'
                    ''.format(request.uuid))
        print('Stopping execution as requested by request {}'
              ''.format(request.uuid))
        stop_threads()
        # The console interface has turned off the stty echo to enable the
        # autocomplete feature (this is done by the readline library).
        # So we have to re-enable it before exiting
        if console_interface is not None and console_interface.uses_tty:
            system('stty echo')
        LOGGER.info('Execution terminated')
        print('Execution terminated')
    except KeyboardInterrupt:
        LOGGER.info('Stopping execution as requested by KeyboardInterrupt')
        print('Stopping execution as requested by KeyboardInterrupt')
        stop_threads()
        # Re-enable the terminal echo as for SystemExit
        if console_interface is not None and console_interface.uses_tty:
            system('stty echo')
        LOGGER.info('Execution terminated')
        print('Execution terminated')
