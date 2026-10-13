#!/bin/bash

SSHD_CONFIG="/etc/ssh/sshd_config"

if [[ ! -f "$SSHD_CONFIG" ]]; then
    echo "ERROR: $SSHD_CONFIG not found."
    exit 1
fi

# Uncomment #PermitRootLogin and set it to 'no'
sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"

if grep -q '^PermitRootLogin no' "$SSHD_CONFIG"; then
    echo "Successfully set PermitRootLogin no in $SSHD_CONFIG"
else
    echo "ERROR: Update failed or line was not found."
    exit 1
fi

# Append CIS remediation lines if not already present
if ! grep -q 'CIS Remediation - content_rule_sshd_limit_user_access' "$SSHD_CONFIG"; then
    cat >> "$SSHD_CONFIG" << 'EOF'

# CIS Remediation - content_rule_sshd_limit_user_access
#DenyUsers root
#AllowUsers *
#DenyGroups root
#AllowGroups *
EOF
    echo "Successfully appended CIS remediation lines to $SSHD_CONFIG"
else
    echo "CIS remediation lines already present, skipping."
fi
