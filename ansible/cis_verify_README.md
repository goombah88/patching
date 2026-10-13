# cis_verify.yml — Post-CIS Hardening Verification Playbook

Verifies that core server functionality is intact after applying CIS benchmark
hardening. The playbook runs all checks regardless of individual failures, logs
a per-check pass/fail table to each host, and prints a summary in the Ansible
play output.

---

## Requirements

- Ansible 2.12+
- Target hosts in the `linux` inventory group
- `become: true` access (sudo) on each target
- `realmd` / `sssd` installed on targets for AD checks

---

## Quick Start

```bash
# Run against all linux hosts
ansible-playbook -i inventory.ini cis_verify.yml

# Run against a single host
ansible-playbook -i inventory.ini cis_verify.yml \
  --limit rcd09-c1-vm-myserver-01

# Pass AD-specific variables
ansible-playbook -i inventory.ini cis_verify.yml \
  -e "ad_domain=example.corp ad_test_user=svc_ansible"

# Dry-run (check mode) — note: some shell tasks will be skipped
ansible-playbook -i inventory.ini cis_verify.yml --check
```

---

## Variables

| Variable | Default | Description |
|---|---|---|
| `log_base_dir` | `./cis_verify_logs` | Base directory **on the AWX controller** where logs are written |
| `log_dir` | `<log_base_dir>/<hostname>-<YYYY-MM-DD>-<HHMMSS>` | Per-run directory, auto-derived from `log_base_dir` + hostname + timestamp |
| `log_file` | `<log_dir>/cis_verify.log` | Final log path, auto-derived from `log_dir` |
| `ad_domain` | `''` | AD domain name used for DNS resolution test. If empty the test resolves `google.com` instead |
| `ad_test_user` | `''` | AD username to verify via `getent passwd`. Skipped if empty |
| `ntp_servers` | `[]` | Reserved for future NTP server validation |

Variables can be set in `group_vars/linux.yml`, host vars, or passed with `-e`.

---

## Checks Performed

The playbook runs 12 check categories. None of them stop execution — every check
always runs to completion.

### 1. SSH
- Confirms `sshd` (or `ssh`) service is in `running` state
- Dumps key `sshd -T` effective settings to the log:
  `permitrootlogin`, `passwordauthentication`, `pubkeyauthentication`,
  `protocol`, `permitemptypasswords`, `usepam`

### 2. Active Directory / SSSD / realmd
- Confirms `sssd` service is running
- Runs `realm list` and checks that output is non-empty (domain enrolled)
- Logs the `domains =` line from `/etc/sssd/sssd.conf`
- If `ad_test_user` is set: runs `getent passwd <user>` to confirm the AD user
  resolves through SSSD (no authentication — read-only lookup)

### 3. PAM
- Checks `/etc/pam.d/sshd` exists
- Checks `/etc/pam.d/common-auth` (Debian/Ubuntu) or `/etc/pam.d/system-auth`
  (RHEL/CentOS) exists
- Scans `/etc/pam.d/` for files that reference `pam_sss` and logs them

### 4. Sudo
- Confirms `/etc/sudoers` exists
- Runs `visudo -c -f /etc/sudoers` to validate syntax

### 5. DNS Resolution
- Runs `getent hosts <ad_domain>` (or `google.com` if `ad_domain` is unset)
- Logs the resolved address

### 6. Time Synchronisation
- Checks `chronyd` / `chrony` or `systemd-timesyncd` is running
- If chrony is running, logs `chronyc tracking` output (reference, offset, etc.)

### 7. Firewall
- **Debian/Ubuntu:** runs `ufw status` and checks for `Status: active`
- **RHEL/CentOS:** checks `firewalld` service state

### 8. Mandatory Access Control
- **Debian/Ubuntu:** runs `aa-status --complaining` to confirm AppArmor is active
- **RHEL/CentOS:** runs `getenforce` and checks for `Enforcing` or `Permissive`

### 9. auditd
- Confirms `auditd` service is in `running` state

### 10. rsyslog
- Confirms `rsyslog` service is in `running` state

### 11. CIS Spot Checks (informational)
These are logged as `[INFO]` lines and do not contribute to pass/fail counts.

| Item | Command |
|---|---|
| umask | `grep "^umask"` across `/etc/profile`, `/etc/profile.d/`, `/etc/bashrc` |
| Password max age | `grep "^PASS_MAX_DAYS"` in `/etc/login.defs` |
| `/tmp` mount | `findmnt /tmp` |
| Core dumps | `grep "hard.*core"` in `/etc/security/limits.conf` and `limits.d/` |

### 12. Listening Ports (informational)
- Runs `ss -tlnup` (falls back to `netstat -tlnup`) and logs all listening
  TCP/UDP services for manual review

---

## Output

### Log file on the AWX controller

Logs are written **locally on the AWX controller** (not on the target hosts)
under `./cis_verify_logs/` by default. Each run gets its own directory:

```
cis_verify_logs/
  rcd09-c1-vm-myserver-01-2026-02-23-101500/
    cis_verify.log
  rcd09-c1-vm-myserver-02-2026-02-23-101501/
    cis_verify.log
```

Override the base directory with `-e log_base_dir=/path/to/logs`.

```
============================================================
CIS Post-Hardening Verification
Host   : rcd09-c1-vm-myserver-01
Date   : 2026-02-23T10:15:00Z
OS     : Ubuntu 24.04
============================================================
[PASS] SSH  : sshd service is running
[INFO] SSH  : permitrootlogin no
[INFO] SSH  : passwordauthentication no
[INFO] SSH  : pubkeyauthentication yes
[INFO] SSH  : usepam yes
[PASS] AD   : sssd service is running
[PASS] AD   : realm enrollment detected
...
============================================================
CHECK RESULTS
------------------------------------------------------------
SSH      : PASS
SSSD     : PASS
REALM    : PASS
PAM      : PASS
SUDO     : PASS
NTP      : PASS
FIREWALL : PASS
MAC      : PASS
AUDITD   : PASS
RSYSLOG  : PASS
------------------------------------------------------------
TOTAL    : 10 passed, 0 failed
FAILED   : none
============================================================
```

### Ansible stdout summary

The final task prints a one-line summary per host in the play output:

```
ok: [rcd09-c1-vm-myserver-01] => {
    "msg": "[ALL PASSED] — log: ./cis_verify_logs/rcd09-c1-vm-myserver-01-2026-02-23-101500/cis_verify.log"
}
```

Or, when failures are present:

```
ok: [rcd09-c1-vm-myserver-01] => {
    "msg": "[CHECKS FAILED] realm, ntp — log: ./cis_verify_logs/rcd09-c1-vm-myserver-01-2026-02-23-101500/cis_verify.log"
}
```

> **Note:** The play itself always returns `ok` (never `failed`) — failures are
> reported inside the message, not as Ansible task failures. This ensures AWX
> runs to completion across all hosts in the inventory even if individual checks
> fail on some servers.

---

## Supported Operating Systems

| OS | Tested versions |
|---|---|
| Ubuntu | 20.04, 22.04, 24.04 |
| CentOS / RHEL | 7.x |

Firewall, AppArmor/SELinux, and package-manager-specific tasks are
automatically selected based on `ansible_facts['os_family']`
(`Debian` vs `RedHat`).

---

## Tips

- **Scope by cluster or OS** — combine with standard Ansible limit patterns:
  ```bash
  ansible-playbook -i inventory.ini cis_verify.yml \
    --limit 'rcd09-c1-vm-vault-*'
  ```

- **Collect logs centrally** — logs are already written locally on the AWX
  controller under `./cis_verify_logs/`. No fetch step needed.

- **AD user lookup** — use a low-privilege service account that exists in AD
  but has no local privileges. The check uses `getent passwd` only (read-only,
  no password needed).

- **Failures are not remediation** — this playbook only reports state. Use your
  CIS hardening role to fix issues, then re-run to verify.
