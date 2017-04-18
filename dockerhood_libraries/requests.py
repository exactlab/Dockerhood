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

from collections import deque
from datetime import datetime, timedelta
from uuid import uuid4 as generate_uuid
from threading import Thread, Lock
from time import sleep
import traceback
import logging

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"

LOGGER = logging.getLogger(__name__)


class Request(object):
    """
    A Request represent the an input from an interface to perform a particular
    operation

    Args:
        - action: a callable object, such that execute action() means
          satisfy the request
    """
    # These are the status that a request can assume
    PENDING = 1
    EXECUTING = 2
    EXECUTED = 3
    ERROR = -1

    def __init__(self, action):
        self.uuid = str(generate_uuid())
        self.creation_time = datetime.now()
        self.action = action
        self.status = Request.PENDING
        # This is the answer that will be returned by the action
        # when it will be executed
        self.answer = None

    def age(self):
        """
        Return the time passed since the creation of this request
        """
        return datetime.now() - self.creation_time

    def execute(self):
        """
        Execute the action of this request. The status of the request will
        change in "EXECUTING" while the action is being performed and
        "EXECUTED" at the end. The return value of the action() function will
        be stored in the answer attribute.
        If calling action() raises an error, the status of the request will be
        set to "ERROR" and the anser attribute will contain the exception
        raised.
        """
        self.status = Request.EXECUTING
        try:
            LOGGER.debug('Executing request {}'.format(self.uuid))
            self.answer = self.action()
            self.status = Request.EXECUTED
            LOGGER.debug('Request {} executed'.format(self.uuid))
        except SystemExit:
            self.status = Request.EXECUTED
            raise
        except:
            err_mesg = traceback.format_exc()
            LOGGER.info('Error in request {}: {}'
                        ''.format(self.uuid, err_mesg))
            traceback_lines = [l for l in err_mesg.split('\n') if l != '']
            self.answer = traceback_lines[-1]
            self.status = Request.ERROR

    def __str__(self):
        return 'request {}'.format(self.uuid)


class RequestManager(Thread):
    """
    The reqest manager is the thread that is in charge of handle the different
    requests raised by the interfaces.
    The workflow is the following:
        - An Interface build an object that must be called to execute a
          particular operation; this object is called "an action"
        - The RequestManager create a request for this operation that will
          wait until the main thread is ready to execute it (the main thread
          could be busy with previous request). While doing this, the
          RequestManager returns an UUID for the Request to the interface.
        - The main thread execute the request. The RequestManager takes care
          of remembering the result of the operation
        - Any Interface can retrieve the result of the request using the UUID
        - After discard_time, the request is deleted because it is not
          useful anymore.

    A request is deleted if the time passed since its creation is greater than
    the discard_time: this is true also for the request that are still in
    PENDING status (and, therefore, not executed).

    Args:
        - stop_value: an object that will be continuously valutated as a
          boolean. If it returns True, the execution will be stopped
        - update_time: the minimum ammount of time between two updates of the
          dockerhood_status in seconds (default: 10)
        - responsiveness: the amount of time between the ticks used to check if
          stop_value is True
        - discard_time (optional): A  timedelta object. By default, it is 1 day.
    """
    def __init__(self, stop_flag, responsiveness=0.5, discard_time=None):
        super(RequestManager, self).__init__()

        # Create a dictionary to associate uuid to requests
        self._request_dict = {}

        # Create a queue for the requests' uuid
        self._request_deque = deque()

        # Create a lock to avoid concurrency when the previous collections
        # are edited
        self._request_lock = Lock()

        self.daemon = True

        self.stop_flag = stop_flag
        self.responsiveness = responsiveness

        if discard_time is None:
            self.discard_time = timedelta(days=1)
        else:
            self.discard_time = discard_time

    def run(self):
        time_passed = 0
        while True:
            sleep(self.responsiveness)
            time_passed += self.responsiveness
            if self.stop_flag:
                break
            if time_passed < 3600:
                continue
            # Because of the previous lines, the following code will be
            # execute just once every 1 hour (3600 seconds)
            LOGGER.debug('Acquiring request lock for discarding the old '
                         'requests')
            self._request_lock.acquire()
            LOGGER.debug('Lock acquired for discarding the old requests')

            # We will create a new empty queue, and we will check each request
            # one by one: if it is too old, it will be discarded, otherwise it
            # will be copied in the new queue
            old_queue = self._request_deque
            self._request_deque = deque()

            LOGGER.debug('{} requests will be checked'.format(len(old_queue)))
            while len(old_queue) > 0:
                uuid = old_queue.popleft()
                request = self._request_dict[uuid]
                if request.age() > self.discard_time:
                    LOGGER.debug('Request {} is {} old and will be deleted'
                                 ''.format(uuid, request.age()))
                    del self._request_dict[uuid]
                else:
                    LOGGER.debug('Request {} is {} old and will NOT be deleted'
                                 ''.format(uuid, request.age()))
                    self._request_deque.append(uuid)

            LOGGER.debug('Releasing request lock acquired for discarding the '
                         'old requests')
            self._request_lock.release()
            LOGGER.debug('Request lock acquired for discarding the old '
                         'requests released')


    def create_request(self, action):
        """
        Starting from an action (a callable object), create a new request and
        put it in the computational queue

        Args:
            - action: a callable object that must be executed to sodisfy the
              request

        Return:
            The UUID of the new request as a string
        """
        LOGGER.debug('A new request must be generated')
        request = Request(action)
        LOGGER.debug(
            'New request generated with the UUID {}'.format(request.uuid)
        )

        LOGGER.debug('Acquiring request lock for request {}'
                     ''.format(request.uuid))
        self._request_lock.acquire()
        LOGGER.debug('Lock acquired for request {}'.format(request.uuid))

        self._request_deque.append(request.uuid)
        self._request_dict[request.uuid] = request

        LOGGER.debug('Releasing request lock (acquired for {})'
                     ''.format(request.uuid))
        self._request_lock.release()

        return request.uuid

    def get_next_request(self):
        """
        Return the next request that must be executed by the main thread
        """
        # I decided to remove the log lines in this function because
        # they were too verbose (this function is called 10 times per second)
        # LOGGER.debug('Acquiring request lock for getting next request')
        self._request_lock.acquire()
        # LOGGER.debug('Lock acquired for getting next request')

        no_new_requests = True
        try:
            next_request_uuid = self._request_deque.popleft()
            no_new_requests = False
        except IndexError:
            pass

        if no_new_requests:
            next_request = None
        else:
            next_request =  self._request_dict[next_request_uuid]

        # LOGGER.debug('Releasing request lock')
        self._request_lock.release()
        # LOGGER.debug('Request lock released')

        return next_request

    def get_request_status(self, request_uuid):
        """
        Return the status of a request starting from its UUID

        Args:
            - request_uuid (str): the UUID of the request the state of which
              will be returned

        Return:
            If UUID matches a valid request, return its status. Otherwise,
            return None
        """
        request = self._request_dict.get(request_uuid, None)
        if request is None:
            return None
        else:
            return request.status

    def get_answer(self, request_uuid):
        """
        Return the answer of a request starting from its UUID

        Args:
            - request_uuid (str): the UUID of the request the answer of which
              will be returned

        Return:
            If UUID matches a valid request, return its answer. Otherwise,
            return None
        """
        request = self._request_dict.get(request_uuid, None)
        if request is None:
            return None
        else:
            return request.answer
