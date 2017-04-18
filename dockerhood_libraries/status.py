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

from threading import Thread, Lock
from time import sleep
import logging

from dockerhood_libraries.configuration_reader import config
from dockerhood_libraries.docker_utilities import image_list
from dockerhood_libraries.container_checks import linker_is_running, \
    linker_exists, slurm_master_host, slurm_master_is_running, worker_list

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


class DockerhoodStatus(object):
    """
    A DockerhoodStatus object reports the current status of the infrastructure.
    When a user perform a query to know some information about the
    infrastructure (running workers, the status of the linker, the docker
    images...), the answer will come from this object.

    This way we avoid the concurrency of perform several queries on the docker
    engine at the same time
    """
    def __init__(self):

        self.linker_exists = False
        self.linker_is_running = False

        self.slurm_master_exists = False
        self.slurm_master_host = None
        self.slurm_master_is_running = False

        self.worker_list = []

        self.images = {}
        for host in config.hosts:
            self.images[host] = []

        self.update()

    def update(self):
        """
        Update the values stored inside the DockerhoodStatus object to reflect
        the current status of the system
        """
        # Update the status of the linker
        self.linker_exists = linker_exists()
        self.linker_is_running = linker_is_running()

        # Update the status of the slurm master
        self.slurm_master_host = slurm_master_host()
        if self.slurm_master_host is None:
            self.slurm_master_exists = False
        else:
            self.slurm_master_exists = True
        self.slurm_master_is_running = slurm_master_is_running()

        # Update the list of the workers
        self.worker_list = worker_list()

        # Update the list of the images
        for host in config.hosts:
            docker_client = host.get_docker_client()
            self.images[host] = [
                i for i in image_list(docker_client)
                if i.startswith(config.project + '_')
            ]

    def __str__(self):
        linker_running = self.linker_is_running
        master_exists = self.slurm_master_exists
        master_running = self.slurm_master_is_running
        master_host = self.slurm_master_host

        output = ""
        output += 'LINKER\n'
        output += 'Linker exists:           {}\n'.format(self.linker_exists)
        output += 'Linker is running:       {}\n\n'.format(linker_running)

        output += 'SLURM MASTER\n'
        output += 'Slurm master exists:     {}\n'.format(master_exists)
        output += 'Slurm master is running: {}\n'.format(master_running)
        output += 'Slurm master on host:    {}\n\n'.format(master_host)

        output += 'WORKERS\n'
        for host in config.hosts:
            output += '- {}\n'.format(host.name)
            for worker in self.worker_list:
                if worker['host'] == host:
                    ext_name = worker['ext name']
                    status = 'active' if worker['active'] else 'stopped'
                    output += '    * {} ({})\n'.format(ext_name, status)
        output += '\n'

        output += 'IMAGES\n'
        for host in config.hosts:
            output += '- {}\n'.format(host.name)
            for image in self.images[host]:
                output += '    * {}\n'.format(image)
        return output


class StatusUpdater(Thread):
    """
    A StatusUpdater is a Thread that runs continuously and updates the
    current status of the system.

    Args:
        - dockerhood_status: the DockerhoodStatus object that represent the
          status of the system
        - stop_value: an object that will be continuously valutated as a
          boolean. If it returns True, the execution will be stopped
        - update_time: the minimum ammount of time between two updates of the
          dockerhood_status in seconds (default: 10)
        - responsiveness: the amount of time between the request for an update
          and the beginning of the execution of the update in seconds
          (default: 0.5)

    """
    def __init__(self, dockerhood_status, stop_flag, update_time=5,
                 responsiveness=0.5):
        super(StatusUpdater, self).__init__()
        # This thread is a daemon and therefore it does not
        # keep the process active when it is the only thread
        # running
        self.daemon = True

        self.dockerhood_status = dockerhood_status
        self.stop_flag = stop_flag

        self._update_time = update_time
        self._resp = responsiveness

        # A boolean that tells if an update must be performed
        # as soon as possible
        self._update_now = False

        # This boolean reports if the requested update has been
        # completed
        self._executed = False

        # A boolean to store if the autmatic updates of the Dockerhood
        # status object must be paused
        self._paused = False

        # A lock to be sure that only one thread at time can request
        # an update
        self.__update_lock = Lock()

    def run(self):
        """
        The function performed by the thread
        """
        time_without_update = 0
        while True:
            LOGGER.debug('StatusUpdater started')
            while self._paused:
                sleep(self._resp)
                time_without_update += self._resp
                if self.stop_flag:
                    break
                if self._update_now:
                    time_without_update = 0
                    self._update_now = False
                    self._update()
                    self._executed = True
                if time_without_update > self._update_time:
                    time_without_update = 0
                    self._update()

            # If the status is paused, sleep until the status is
            # changed or until somebody asks for an update
            LOGGER.debug('StatusUpdater paused')
            while self._paused:
                sleep(self._resp)
                if self.stop_flag:
                    break
                if self._update_now:
                    self._update_now = False
                    self._update()
                    self._executed = True

            if self.stop_flag:
                break

            # Before moving from pause status to active, reset the
            # time_without_update timer
            time_without_update = 0

    def update(self):
        """
        Request an immediate update to the thread
        """
        # Aquire the lock so this is the only thread that is performing
        # the update at the moment
        LOGGER.debug('Acquiring update lock')
        self.__update_lock.acquire()

        # Request for an immediate update
        self._update_now = True
        LOGGER.debug('Request to perform an update sent')

        # Wait until the thread perform the update in the run() function
        while not self._executed:
            sleep(self._resp)

        # set self._executed to the original value, changed by run()
        self._executed = False

        # Release the lock
        LOGGER.debug('Releasing update lock')
        self.__update_lock.release()

    def pause(self):
        """
        Stop the execution of the periodic updates
        """
        LOGGER.debug('Setting the flag to pause the StatusUpdater')
        self._paused = True

    def unpause(self):
        """
        Start the execution of the periodic updates
        """
        LOGGER.debug('Setting the flag to unpause the StatusUpdater')
        self._paused = False

    def _update(self):
        """
        These are the operations that the StatusUpdater will perform
        to update the values of the dockerhood_status
        """
        LOGGER.debug('Updating status')
        self.dockerhood_status.update()
