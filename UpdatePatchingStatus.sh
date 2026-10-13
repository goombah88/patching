#!/bin/bash

# Author: Chad Crider
# Date:   2/21/2024
# Purpose:To allow the server to phone home with patching status updates

[[ -z $1 ]] || [[ -z $2 ]] && echo "Usage: `basename $0` <Patching Step> <Status>" && exit
STEP=$1
STATUS=$2

# Read in the env file to set important variables
. /home/ansible/scripts/patching.env

# This function will create the JSON data packet that will get sent to the patching server.
generate_post_data()
{
  cat <<EOF
{
  "host": "`hostname`",
  "step": "$STEP",
  "status": "$STATUS"
}
EOF
}

# Time to phone home with patching status update
curl --noproxy '*' \
	-i \
	-H "Content-Type: application/json" \
	-X POST \
	-d "$(generate_post_data)" \
	http://$REPO_SERVER:$REPO_SERVER_PORT/patching