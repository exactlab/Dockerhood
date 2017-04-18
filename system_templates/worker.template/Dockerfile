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

FROM {{BASE_IMAGE_NAME}}

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y openvpn python-pip slurm-llnl supervisor

# Set a user and its home
RUN export uid={{UID}} gid={{GID}} && mkdir -p /home/user && echo "user:x:${uid}:${gid}:Main User,,,:/home/user:/bin/bash" >> /etc/passwd && \
    echo 'user:!:16000::::::\n' >> /etc/shadow && \
    echo "user:x:${uid}:" >> /etc/group && chown ${uid}:${gid} -R /home/user && \
    cp /root/.bashrc /home/user/.bashrc && \
    chown ${uid}:${gid} /home/user/.bashrc

# Copy the keys
ADD ca.crt linker-client.crt linker-client.key ta.key /etc/openvpn/

# Add the general configuration for supervisord
{% insert 'supervisor_config.txt' in '/supervisor.conf' %}

# Add the configuration file for the network
{% insert 'openvpn_config.txt' in '/etc/openvpn/{{Q_NAME}}' %}

# Copy the run_and_restart script to restart the slurmd daemon
{% insert 'run_and_restart.py' in '/run_and_restart.py' %}

# Copy the update_hostname.py script
{% insert 'update_hostname.py' in '/update_hostname.py' %}

# Copy the update_fqdn.py script
{% insert 'update_fqdn.py' in '/update_fqdn.py' %}

# Create a file where the Dockername will be saved
RUN echo 'UNSPECIFIED' > /DOCKER_NAME.txt

# Configure supervisor to start the VPN
RUN echo '[program:{{Q_NAME}}]' >> /supervisor.conf && \
    echo 'command=openvpn --config /etc/openvpn/{{Q_NAME}}' >> /supervisor.conf && \
    echo 'autostart=true' >> /supervisor.conf && \
    echo 'startsecs=10' >> /supervisor.conf && \
    echo 'autorestart=false' >> /supervisor.conf && \
    echo 'stopwaitsecs=60' >> /supervisor.conf && \
    echo '' >> /supervisor.conf

# The setup for the network is complete. Let's install munge to handle the authentication in slurm
RUN mkdir -p /var/run/munge && \
    mkdir -p /var/run/slurm-llnl

COPY munge.key /etc/munge/munge.key

# Add the slurm configuration file
{% insert 'slurm_config.txt' in '/etc/slurm-llnl/slurm.conf' %}

RUN chown munge:munge /etc/munge/munge.key && \
    chmod 0400 /etc/munge/munge.key

# Define the nodes for slurm
RUN echo '# COMPUTE NODES' >> /etc/slurm-llnl/slurm.conf && \
{% for q in queues %}
    echo 'NodeName={{q.name}}-WORKER-INT[2-255] NodeAddr={{q.ip_fixed_part}}.[2-255] State=UNKNOWN' >> /etc/slurm-llnl/slurm.conf && \
{% end_for %}
    echo '' >> /etc/slurm-llnl/slurm.conf

# Define the partitions for slurm
RUN echo '# PARTITIONS' >> /etc/slurm-llnl/slurm.conf && \
{% for q in queues %}
    echo 'PartitionName={{q.name}} Nodes={{q.name}}-WORKER-INT[2-255] Default=YES MaxTime=INFINITE State=UP' >> /etc/slurm-llnl/slurm.conf && \
{% end_for %}
    echo '' >> /etc/slurm-llnl/slurm.conf

RUN pip install netifaces

CMD ["supervisord","--config","/supervisor.conf"]
