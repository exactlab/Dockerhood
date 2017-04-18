from __future__ import print_function

"""
This script checks if the tun0 interface (the interface of the VPN) is up and,
if this is the case, reads its IP.
At that point, it ensures that the hostname of the running host is
$MY_QUEUE-WORKER-INT$i
where $MY_QUEUE is the value of the variables hard-coded in this script and $i
is the last number of the IP.
The reason to do that is that this is the hostname SLURM expects in its
configuration files.
"""

import sys
import socket
import netifaces
import time
import traceback
import subprocess

MY_QUEUE = '{{Q_NAME}}'

def check_if_interface_exists(interface_name):
    return interface_name in netifaces.interfaces()

def get_interface_address(interface_name):
    return netifaces.ifaddresses(interface_name)[netifaces.AF_INET][0]['addr']

if __name__ == '__main__':
    while True:
        try:
            # sleep must be here to ensure that some exception
            # in the following lines
            time.sleep(10)

            # Check if the virtual interface is up
            tun0_exists = check_if_interface_exists('tun0')
            if not tun0_exists:
                continue

            # Get the ip of the virtual interface
            addr = get_interface_address('tun0')

            # Get the last number of the IP
            last_number = int(addr.split('.')[-1])

            # This is the expected hostname for this host
            hostname_attempt = '{}-WORKER-INT{}'.format(MY_QUEUE, last_number)

            if socket.gethostname() != hostname_attempt:
                # Change hostname using the attempt
                subprocess.check_call(['hostname', hostname_attempt])
                message = 'Hostname changed in {}'.format(hostname_attempt)
                print(message, file=sys.stderr)

        except KeyboardInterrupt:
            raise
        except:
            traceback.print_exc()
