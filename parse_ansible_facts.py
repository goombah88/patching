#!/usr/bin/env python3
"""
Parse Ansible facts from multiple files and output to CSV.

Usage:
    python parse_ansible_facts.py <directory_path> [output.csv]
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def parse_facts_file(file_path):
    """Parse a single Ansible facts file and extract required fields."""
    try:
        with open(file_path, "r") as f:
            facts = json.load(f)

        # Handle both direct facts and nested ansible_facts structure
        if "ansible_facts" in facts:
            facts = facts["ansible_facts"]

        # Try both with and without ansible_ prefix
        hostname = facts.get("ansible_hostname") or facts.get("hostname") or "N/A"
        os_family = facts.get("ansible_distribution") or facts.get("distribution") or "N/A"
        os_version = (
            facts.get("ansible_distribution_version") or facts.get("distribution_version") or "N/A"
        )

        return {
            "hostname": hostname,
            "os_family": os_family,
            "os_version": os_version,
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Parse Ansible facts from directory and output to CSV"
    )
    parser.add_argument("directory", help="Directory containing Ansible facts files")
    parser.add_argument(
        "output",
        nargs="?",
        default="server_facts.csv",
        help="Output CSV file (default: server_facts.csv)",
    )

    args = parser.parse_args()

    # Validate directory
    directory = Path(args.directory)
    if not directory.exists():
        print(f"Error: Directory {directory} does not exist", file=sys.stderr)
        sys.exit(1)

    if not directory.is_dir():
        print(f"Error: {directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Process all files in directory
    results = []
    file_count = 0

    for file_path in sorted(directory.iterdir()):
        if file_path.is_file():
            file_count += 1
            parsed = parse_facts_file(file_path)
            if parsed:
                results.append(parsed)

    # Write to CSV
    if results:
        with open(args.output, "w", newline="") as csvfile:
            fieldnames = ["Hostname", "OS Family", "OS Version"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "Hostname": result["hostname"],
                        "OS Family": result["os_family"],
                        "OS Version": result["os_version"],
                    }
                )

        print(f"Processed {len(results)} of {file_count} files")
        print(f"Output written to {args.output}")
    else:
        print("No valid facts files found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
