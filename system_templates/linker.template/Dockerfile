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
    apt-get install -y openvpn supervisor

# Set a user and its home
# RUN export uid={{UID}} gid={{GID}} && mkdir -p /home/user && echo "user:x:${uid}:${gid}:Main User,,,:/home/user:/bin/bash" >> /etc/passwd && \
RUN export uid=1000 gid=1000 && mkdir -p /home/user && echo "user:x:${uid}:${gid}:Main User,,,:/home/user:/bin/bash" >> /etc/passwd && \
    echo 'user:!:16000::::::\n' >> /etc/shadow && \
    echo "user:x:${uid}:" >> /etc/group && chown ${uid}:${gid} -R /home/user && \
    cp /root/.bashrc /home/user/.bashrc && \
    chown ${uid}:${gid} /home/user/.bashrc

# Copy the keys
ADD ca.crt ca.key linker.crt linker.key ta.key dh2048.pem /etc/openvpn/

# Create a directory for the logs
RUN mkdir /var/log/links

# Add the general configuration for supervisord
{% insert 'supervisor_config.txt' in '/supervisor.conf' %}

# Add the configuration file for the static network
{% insert 'openvpn_static_config.txt' in '/etc/openvpn/STATIC-NETWORK' %}

RUN echo '[program:STATIC-NETWORK]' >> /supervisor.conf && \
    echo 'command=openvpn --config /etc/openvpn/STATIC-NETWORK' >> /supervisor.conf && \
    echo 'autostart=true' >> /supervisor.conf && \
    echo 'startsecs=10' >> /supervisor.conf && \
    echo 'autorestart=false' >> /supervisor.conf && \
    echo 'stopwaitsecs=60' >> /supervisor.conf && \
    echo '' >> /supervisor.conf

# Create a configuration file for each queue
{% for q in queues %}
  {% insert 'openvpn_config.txt' in '/etc/openvpn/{{q.name}}' %}

  RUN echo '' >> /etc/openvpn/{{q.name}} && \
      echo '# Configure the routes to allow the machines to speak' >> /etc/openvpn/{{q.name}} && \
      echo '# even with the machines that are on the other VPNs' >> /etc/openvpn/{{q.name}} && \
      echo 'push "route {{STATIC_NETWORK}} 255.255.255.0"' >> /etc/openvpn/{{q.name}} && \
      {% for oq in queues %}
        echo 'push "route {{oq.subnet}} 255.255.255.0"' >> /etc/openvpn/{{q.name}} && \
      {% end_for %}
      echo '' >> /etc/openvpn/{{q.name}} 

  RUN echo '[program:{{q.name}}]' >> /supervisor.conf && \
      echo 'command=openvpn --config /etc/openvpn/{{q.name}}' >> /supervisor.conf && \
      echo 'autostart=true' >> /supervisor.conf && \
      echo 'startsecs=10' >> /supervisor.conf && \
      echo 'autorestart=false' >> /supervisor.conf && \
      echo 'stopwaitsecs=60' >> /supervisor.conf && \
      echo '' >> /supervisor.conf

{% end_for %}

CMD ["supervisord","--config","/supervisor.conf"]
