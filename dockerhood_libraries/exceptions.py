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
The exception module stores all the exceptions that DockerHood raises during
its execution
"""

__author__ = 'Stefano Piani <stefano.piani@exact-lab.it>'
__copyright__ = "Copyright 2016, eXact-lab"


class InvalidIP(ValueError):
    """
    An exception that is raised when a string that should represent an IPv4 is
    submitted but this string is invalid or malformed
    """
    pass


class InvalidNetworkIP(InvalidIP):
    """
    An exception that is raised when a string that should represent a the
    address of a network is submitted but this string is invalid or malformed
    """
    pass


class InvalidPort(ValueError):
    """
    An exception that is raised when a the user choose a port for a network that
    is outside the valid range
    """
    pass


class InvalidProjectName(ValueError):
    """
    An exception that is raised when a the user choose a project name in the
    main configuration file that is not valid because it contains invalid chars
    or it is somehow malformed
    """
    pass


class IpConflict(ValueError):
    """
    An exception raised when two containers try to use the same Ip in a VPN
    """
    pass


class InvalidQueue(ValueError):
    """
    An exception that is raised when a request is performed on a non-existent
    computational queue
    """
    pass


class InvalidHostname(ValueError):
    """
    An exception that is raised when a request is performed involving a
    non-existent host name
    """
    pass


class ImageMissing(Exception):
    """
    An exception that is raised when there is a request for creating a
    container but the needed image is missing
    """
    pass


class ImageNotFromATemplate(Exception):
    """
    An exception that is raised when there is a request for changing, deleting,
    or creating an image that does not come from a template and that, therefore,
    should not be managed by DockerHood
    """
    pass


class ImageAlreadyBuilt(Exception):
    """
    An exception that is raised when there is a request for creating an
    image that has already been built
    """
    pass


class ImageInUse(Exception):
    """
    An exception that is raised when there is a request for deleting an
    image that is linked to existing containers
    """
    pass


class ImageNotFound(Exception):
    """
    An exception that is raised when there is a request for some operations on
    a specific image that does not exist
    """
    pass


class BaseImageNotBuilt(ImageNotFound):
    """
    An exception that is raised when there is a request for build an image from
    the base image, but the base image has not been built
    """
    pass


class OnlyOneInstanceAllowed(Exception):
    """
    An instance that is raised when there is a request for starting an
    instance of a container for which one instance is already running
    and two simultaneous instances are not allowed
    """
    pass


class ContainerAlreadyStarted(Exception):
    """
    An exception that is raised when there is a request for starting a docker
    container which is already running
    """
    pass


class ContainerAlreadyStopped(Exception):
    """
    An exception that is raised when there is a request for stopping a docker
    container which is not running
    """
    pass


class ContainerNotFound(Exception):
    """
    An exception that is raised when there is a request for some operations on
    a specific container that does not exist
    """
    pass


class LinkerAlreadyStarted(ContainerAlreadyStarted):
    """
    An exception that is raised when there is a request for starting the linker,
    but the linker is already running
    """
    pass


class LinkerAlreadyStopped(ContainerAlreadyStopped):
    """
    An exception that is raised when there is a request for stopping the linker,
    but the linker is not running
    """
    pass


class LinkerNotFound(ContainerNotFound):
    """
    An exception that is raised when there is a request for some operations on
    the linker but the linker has never been created
    """
    pass


class WorkerNotFound(ContainerNotFound):
    """
    An exception that is raised when there is a request for some operations on
    a worker that has never been created
    """
    pass


class WorkerAlreadyStarted(ContainerAlreadyStarted):
    """
    An exception that is raised when there is a request for starting a worker
    container which is already running
    """
    pass


class WorkerAlreadyStopped(ContainerAlreadyStopped):
    """
    An exception that is raised when there is a request for stopping a worker
    container which is not running
    """
    pass


class QueueIsFull(Exception):
    """
    An exception that is raised when there is a request for start a new
    container in a queue that already hosts 254 other containers
    """
    pass
