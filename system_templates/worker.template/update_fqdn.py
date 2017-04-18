from __future__ import print_function

"""
This script changes the /etc/hosts file in such a way that the command::

  hostname -f

returns the name of the docker where this script is running.
The name of the docker is expected to be written in the file
/DOCKER_NAME.txt
This script reads this file, read the hostname and writes the line
127.0.0.1 DOCKER_NAME hostname
in the /etc/hosts file
"""

import socket
import time
import traceback


def read_fqdn():
    try:
        with open('/DOCKER_NAME.txt', 'r') as f:
            content = f.readlines()
        docker_name = content[0].split()[0]
        return docker_name
    except:
        traceback.print_exc()
        return 'UNSPECIFIED'

def read_hostname():
    return socket.gethostname()

if __name__ == '__main__':
    while True:
        try:
            # sleep must be here to ensure that an exception
            # in the following lines does not make the script
            # writing tons of log lines
            time.sleep(3)

            # Read the name of the docker
            docker_name = read_fqdn()

            # Read the hostname
            hostname = read_hostname()

            # Read the /etc/hosts file
            with open('/etc/hosts', 'r') as f:
                hosts = f.readlines()

            # A boolean that remembers if some edits on the file have
            # been made
            line_changed = False

            # The line that must be in the /etc/hosts file to
            # be able to resolve the name
            magic_line = '127.0.0.1 {} localhost {}\n'\
                          ''.format(docker_name, hostname)

            # Change the line that starts with 127.0.0.1 if that line is not
            # the magic line
            for i, host_line in enumerate(hosts):
                if host_line.startswith('127.0.0.1'):
                    if host_line != magic_line:
                        hosts[i] = magic_line
                        line_changed = True
                    break
                else:
                    # if no line starts with 127.0.0.1, this line will be
                    # inserted
                    new_hosts = [magic_line,]
                    new_hosts.extend(hosts)
                    hosts = new_hosts
                    line_changed = True

            # If we changed something, we have to rewrite the /etc/hosts file
            if line_changed:
                with open('/etc/hosts', 'w') as f:
                    f.write(''.join(hosts))

        except KeyboardInterrupt:
            raise
        except:
            traceback.print_exc()
