#!/bin/bash

# Author: Chad Crider
# Date:   1/8/2024
# Purpose:To set up APT to not use the proxy for our local OS repo
#		otherwise it'll fail.
#	  All 3rd party repos will still use the proxy.

PROXY_CONFIG="/etc/apt/apt.conf.d/80proxy"

# First move any old config out of the way, just in case
[[ -f $PROXY_CONFIG ]] && mv $PROXY_CONFIG /home/ansible/80proxy.old

# Now write the new one
echo -e "Acquire{\n
\t# Use DIRECT for local repositories on the local network
\thttp::proxy::172.16.150.49 \"DIRECT\";
\thttp::proxy \"http://proxy.esl.cisco.com:80\";
\t# The following can be used as an alernative if needing to be more
\t# specific in which sites to allow the proxy server.
\t# http::proxy::download.docker.com \"http://proxy.esl.cisco.com:80\";
}
Acquire{
\thttps::proxy::172.16.150.49:80 \"DIRECT\";
\thttps::proxy \"http://proxy.esl.cisco.com:80\";
}
Acquire::ftp::proxy \"ftp://proxy.esl.cisco.com:80\";" > $PROXY_CONFIG

chmod 644 $PROXY_CONFIG
chown root:root $PROXY_CONFIG