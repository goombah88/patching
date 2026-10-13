#!/bin/bash

GRUB_FILE="/etc/grub.d/10_linux"

if [[ ! -f "$GRUB_FILE" ]]; then
    echo "ERROR: $GRUB_FILE not found."
    exit 1
fi

sed -i '/^CLASS="/ { /--unrestricted/! s/"$/ --unrestricted"/ }' "$GRUB_FILE"

if grep -q -- '--unrestricted' "$GRUB_FILE"; then
    echo "Successfully updated CLASS in $GRUB_FILE"
else
    echo "ERROR: Update failed or line was not found."
    exit 1
fi
