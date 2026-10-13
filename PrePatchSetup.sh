#!/bin/bash

# PrePatch script.
# Make sure server is ready for patching

# Look for some key files used for patching and make sure they're present
for FILE in patching.env UpdatePatchingStatus.sh SetAPTProxy.sh; do
	echo $FILE
	if [[ $FILE == "patching.env" ]]; then
		if [[ -f patching.env ]]; then
			. patching.env
		else
			echo "PROBLEM. File \"patching.env\" missing"
			echo "PROBLEM. File \"patching.env\" missing"
		fi
	else
		if [[ ! -f $FILE ]]; then
			echo "PROBLEM. File \"$FILE\" missing"
		fi
	fi
done

# Clean up apt cache
sudo apt clean all

# Make sure we can ping the Repo Server
if ping -c 3 "$REPO_SERVER" >/dev/null 2>&1; then
	echo "Patching Server $REPO_SERVER reachable"
else
	echo "PROBLEM. Unable to ping Patching Server $REPO_SERVER"
fi

# Make sure VM Tools is installed
[[ ! `/usr/bin/dpkg -l | grep open-vm-tools` ]] && sudo apt install -y open-vm-tools