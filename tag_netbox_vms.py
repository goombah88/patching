#!/usr/bin/env python3
import argparse
import getpass
import os
import re
import sys
from typing import Iterable, List

import pynetbox
from pynetbox.core.query import RequestError


NETBOX_BASE_URL = "http://netbox.systems.cll.cloud"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add a NetBox tag to virtual machines listed in a file. "
            "VMs are matched by exact name."
        )
    )
    parser.add_argument("--file", required=True, help="Path to file with VM names")
    parser.add_argument("--tag", default="NO_AWX_INV", help="Tag to add")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without updating NetBox",
    )
    return parser.parse_args()


def normalize_url(url: str) -> str:
    return url.rstrip("/")


def prompt_token() -> str:
    token = ""
    while not token:
        token = getpass.getpass("NetBox token (r/w): ").strip()
    return token


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "tag"


def parse_names(lines: Iterable[str]) -> List[str]:
    names: List[str] = []
    seen = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(r"\[([^\]]+)\]", line)
        if match:
            name = match.group(1).strip()
        else:
            name = line.split("#", 1)[0].strip()
            name = name.split(":", 1)[0].strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def get_or_create_tag(api: pynetbox.api, tag_name: str):
    tag = api.extras.tags.get(name=tag_name)
    if tag:
        return tag
    return api.extras.tags.create({"name": tag_name, "slug": slugify(tag_name)})


def resolve_tag_ids(api: pynetbox.api, tags: Iterable) -> List[int]:
    ids: List[int] = []
    seen = set()
    for tag in tags or []:
        tag_id = None
        tag_name = None
        if isinstance(tag, dict):
            tag_id = tag.get("id")
            tag_name = tag.get("name")
        else:
            tag_id = getattr(tag, "id", None)
            tag_name = getattr(tag, "name", None)

        if tag_id is None and tag_name:
            existing = api.extras.tags.get(name=tag_name)
            tag_id = getattr(existing, "id", None) if existing else None

        if tag_id is None:
            continue

        if tag_id not in seen:
            seen.add(tag_id)
            ids.append(tag_id)
    return ids


def update_vm_tag(
    api: pynetbox.api,
    vm_name: str,
    tag,
    dry_run: bool,
) -> str:
    vms = list(api.virtualization.virtual_machines.filter(name=vm_name))
    if not vms:
        return "not-found"
    if len(vms) > 1:
        return "multiple"

    vm = vms[0]
    current_tag_ids = resolve_tag_ids(api, vm.tags)
    if getattr(tag, "id", None) in current_tag_ids:
        return "already-tagged"

    new_tags = list(current_tag_ids)
    if getattr(tag, "id", None) not in current_tag_ids:
        new_tags.append(tag.id)
    if dry_run:
        return "would-tag"

    vm.tags = new_tags
    vm.save()
    return "tagged"


def main() -> int:
    args = parse_args()
    base_url = normalize_url(NETBOX_BASE_URL)
    token = os.environ.get("NETBOX_TOKEN") or prompt_token()

    with open(args.file, "r", encoding="utf-8") as handle:
        vm_names = parse_names(handle.readlines())

    if not vm_names:
        print("No VM names found.")
        return 1

    api = pynetbox.api(base_url, token=token)
    api.http_session.verify = not args.insecure

    try:
        tag = get_or_create_tag(api, args.tag)
    except RequestError as exc:
        print(f"Failed to ensure tag {args.tag}: {exc}")
        return 2

    results = {
        "tagged": 0,
        "already-tagged": 0,
        "would-tag": 0,
        "not-found": 0,
        "multiple": 0,
        "error": 0,
    }

    for name in vm_names:
        try:
            status = update_vm_tag(api, name, tag, args.dry_run)
            results[status] += 1
            print(f"{name}: {status}")
        except RequestError as exc:
            results["error"] += 1
            print(f"{name}: error ({exc})")

    print("---")
    print(
        "Summary: "
        f"tagged={results['tagged']} "
        f"would-tag={results['would-tag']} "
        f"already-tagged={results['already-tagged']} "
        f"not-found={results['not-found']} "
        f"multiple={results['multiple']} "
        f"error={results['error']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
