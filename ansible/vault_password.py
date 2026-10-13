#!/usr/bin/env python3
"""Retrieve an Ansible password from HashiCorp Vault.

Required environment variables:
- VAULT_URL
- VAULT_TOKEN
- VAULT_SECRET_PATH (including mount, e.g. "secret/path/to/creds")

Optional:
- VAULT_PASSWORD_KEY (defaults to "password")
"""

import os
import sys
import hvac


def _parse_mount_and_path(secret_path):
    parts = secret_path.split("/", 1)
    if len(parts) < 2:
        raise ValueError("VAULT_SECRET_PATH must include mount prefix, e.g. 'secret/path/to/creds'")
    return parts[0], parts[1]


def main():
    vault_url = os.environ.get("VAULT_URL")
    vault_token = os.environ.get("VAULT_TOKEN")
    secret_path = os.environ.get("VAULT_SECRET_PATH")
    password_key = os.environ.get("VAULT_PASSWORD_KEY", "password")

    if not vault_url or not vault_token or not secret_path:
        raise ValueError("VAULT_URL, VAULT_TOKEN, and VAULT_SECRET_PATH are required")

    client = hvac.Client(url=vault_url, token=vault_token)
    if not client.is_authenticated():
        raise ValueError("Vault authentication failed")

    mount_point, path_without_mount = _parse_mount_and_path(secret_path)
    secret = client.secrets.kv.v2.read_secret_version(
        path=path_without_mount,
        mount_point=mount_point,
    )
    data = secret["data"]["data"]
    password = data.get(password_key)
    if not password:
        raise ValueError(f"Password key '{password_key}' not found in Vault data")

    sys.stdout.write(str(password))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"Vault error: {exc}\n")
        sys.exit(1)
