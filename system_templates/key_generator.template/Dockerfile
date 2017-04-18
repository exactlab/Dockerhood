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

FROM ubuntu:16.04

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y easy-rsa openvpn

# Set a user and its home
RUN export uid={{UID}} gid={{GID}} && mkdir -p /home/user && echo "user:x:${uid}:${gid}:Main User,,,:/home/user:/bin/bash" >> /etc/passwd && \
    echo 'user:!:16000::::::\n' >> /etc/shadow && \
    echo "user:x:${uid}:" >> /etc/group && chown ${uid}:${gid} -R /home/user && \
    cp /root/.bashrc /home/user/.bashrc && \
    chown ${uid}:${gid} /home/user/.bashrc

RUN make-cadir /etc/openvpn/easy-rsa
RUN mkdir /etc/openvpn/easy-rsa/keys    
RUN cd /etc/openvpn/easy-rsa && \
    sed -i 's%"$EASY_RSA/pkitool" --interact%"$EASY_RSA/pkitool"%g' build-key-server && \
    sed -i 's%"$EASY_RSA/pkitool" --interact%"$EASY_RSA/pkitool"%g' build-key && \
    sed -i 's%export KEY_COUNTRY="US"%export KEY_COUNTRY="{{KEY_COUNTRY}}"%g' vars && \
    sed -i 's%export KEY_PROVINCE="CA"%export KEY_PROVINCE="{{KEY_PROVINCE}}"%g' vars && \
    sed -i 's%export KEY_CITY="SanFrancisco"%export KEY_CITY="{{KEY_CITY}}"%g' vars && \
    sed -i 's%export KEY_ORG="Fort-Funston"%export KEY_ORG="{{KEY_ORG}}"%g' vars && \
    sed -i 's%export KEY_EMAIL="me@myhost.mydomain"%export KEY_EMAIL="{{KEY_EMAIL}}"%g' vars && \
    sed -i 's%export KEY_OU="MyOrganizationalUnit"%export KEY_OU="{{KEY_OU}}"%g' vars && \
    sed -i 's%export KEY_NAME="EasyRSA"%export KEY_NAME="{{KEY_NAME}}"%g' vars

RUN echo "#!/bin/bash" > /generate_key.sh && \
    echo "" >> /generate_key.sh && \
    echo "set -e" >> /generate_key.sh && \
    echo "" >> /generate_key.sh && \
    echo "cd /etc/openvpn/easy-rsa" >> /generate_key.sh && \
    echo "source ./vars" >> /generate_key.sh && \
    echo "./clean-all" >> /generate_key.sh && \
    echo 'yes ""| ./build-ca' >> /generate_key.sh && \
    echo "./build-key-server linker" >> /generate_key.sh && \
    echo "./build-dh" >> /generate_key.sh && \
    echo "./build-key linker-client" >> /generate_key.sh && \
    echo "openvpn --genkey --secret keys/ta.key" >> /generate_key.sh && \
    echo "cd /home/user/keys" >> /generate_key.sh && \
    echo "rm -vf *" >> /generate_key.sh && \
    echo "for i in ca.crt ca.key ta.key dh2048.pem linker.crt linker.csr linker.key linker-client.crt linker-client.csr linker-client.key" >> /generate_key.sh && \
    echo "  do" >> /generate_key.sh && \
    echo '    cp /etc/openvpn/easy-rsa/keys/$i .' >> /generate_key.sh && \
    echo '    chown user:user $i' >> /generate_key.sh && \
    echo "  done" >> /generate_key.sh

CMD /bin/bash generate_key.sh
