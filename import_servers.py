#!/usr/bin/env python3
"""Upload a CSV of the current patching cycle to the API.

Example:
    python import_servers.py --csv /path/to/netbox.csv --url http://localhost:9999
"""

import argparse
import mimetypes
import os
import sys
import uuid
import urllib.request
import urllib.error


def build_multipart(field_name, filename, content):
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "text/csv"
    parts = [
        f"--{boundary}",
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"',
        f"Content-Type: {content_type}",
        "",
    ]
    body = "\r\n".join(parts).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def main():
    parser = argparse.ArgumentParser(description="Import patching cycle servers")
    parser.add_argument("--csv", required=True, help="Path to NetBox CSV export")
    parser.add_argument(
        "--url",
        default="http://localhost:9999",
        help="Base URL of the patching API (default: http://localhost:9999)",
    )
    parser.add_argument(
        "--multipart",
        action="store_true",
        help="Send CSV as multipart/form-data instead of raw body",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        raise FileNotFoundError(f"CSV not found: {args.csv}")

    with open(args.csv, "rb") as handle:
        content = handle.read()

    if args.multipart:
        body, content_type = build_multipart(
            "file",
            os.path.basename(args.csv),
            content,
        )
    else:
        body = content
        content_type = "text/csv"
    endpoint = args.url.rstrip("/") + "/api/servers/import"

    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", content_type)
    request.add_header("Content-Length", str(len(body)))

    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            sys.stdout.write(payload + "\n")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(payload + "\n")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"Import failed: {exc}\n")
        sys.exit(1)
