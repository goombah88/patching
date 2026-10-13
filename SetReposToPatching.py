#!/usr/bin/env python3

import shutil
import fileinput

REPO_SERVER = "172.16.150.49"
REPO_PATH = f"{REPO_SERVER}/ubuntu/archive.ubuntu.com"
APT_FILE = "/etc/apt/sources.list"
APT_BACKUP_FILE = "/etc/apt/sources.list.public_repos"

# First make a backup
shutil.copyfile(APT_FILE, APT_BACKUP_FILE)

with fileinput.input(APT_FILE, inplace=True, encoding="ASCII") as f:
    for line in f:
        # Touch only the repo lines
        # Skip lines that have already been altered
        if (line.startswith("deb ")) and (REPO_SERVER not in line):
            if "us.archive.ubuntu.com" in line:
                modified_line = line.replace("us.archive.ubuntu.com", REPO_PATH)
                print(modified_line, end="")
            elif "archive.ubuntu.com" in line:
                modified_line = line.replace("archive.ubuntu.com", REPO_PATH)
                print(modified_line, end="")
            elif "us.security.ubuntu.com" in line:
                modified_line = line.replace("us.security.ubuntu.com", REPO_PATH)
                print(modified_line, end="")
            elif "security.ubuntu.com" in line:
                modified_line = line.replace("security.ubuntu.com", REPO_PATH)
                print(modified_line, end="")
            else:
                print(line, end="")
        else:
            print(line, end="")