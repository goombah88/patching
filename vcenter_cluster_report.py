#!/usr/bin/env python3
"""Collect VM names from a vCenter cluster and update server facts.

Requires environment variables:
- VAULT_URL
- VAULT_TOKEN

Optional environment variables:
- VAULT_PASSWORD_KEY (defaults to "password")
"""

import argparse
import csv
import os
import ssl
from pathlib import Path

import hvac
import openpyxl
from openpyxl.styles import Font, PatternFill
from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim

VAULT_SECRET_PATH = (
    "cll/rcd09/c1/vm/rcd09-c1-vm-vcenter-01/" "local-admins/administrator@rcd09.c1.cll.cloud"
)


def parse_mount_and_path(secret_path: str) -> tuple[str, str]:
    parts = secret_path.split("/", 1)
    if len(parts) < 2:
        raise ValueError("Vault path must include mount prefix")
    return parts[0], parts[1]


def get_vault_password() -> str:
    vault_url = os.environ.get("VAULT_URL")
    vault_token = os.environ.get("VAULT_TOKEN")
    password_key = os.environ.get("VAULT_PASSWORD_KEY", "password")

    if not vault_url or not vault_token:
        raise ValueError("VAULT_URL and VAULT_TOKEN are required")

    client = hvac.Client(url=vault_url, token=vault_token)
    if not client.is_authenticated():
        raise ValueError("Vault authentication failed")

    mount_point, path_without_mount = parse_mount_and_path(VAULT_SECRET_PATH)
    secret = client.secrets.kv.v2.read_secret_version(
        path=path_without_mount,
        mount_point=mount_point,
    )
    data = secret["data"]["data"]
    password = data.get(password_key)
    if not password:
        raise ValueError(f"Password key '{password_key}' not found in Vault data")

    return str(password)


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    with env_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _collect_vm_info(vm, cluster_name: str) -> dict:
    config = vm.config
    summary = vm.summary
    guest = vm.guest

    cpu = config.hardware.numCPU if config else ""
    memory_gb = round(config.hardware.memoryMB / 1024, 1) if config else ""

    disk_bytes = (
        (summary.storage.committed or 0) + (summary.storage.uncommitted or 0)
        if summary and summary.storage
        else 0
    )
    disk_gb = round(disk_bytes / (1024**3), 1)

    portgroups = "; ".join(sorted({net.name for net in (vm.network or []) if hasattr(net, "name")}))

    ips: list[str] = []
    if guest and guest.net:
        for nic in guest.net:
            for addr in nic.ipAddress or []:
                if addr not in ips:
                    ips.append(addr)
    ip_str = "; ".join(ips)

    return {
        "Hostname": vm.name,
        "Cluster": cluster_name,
        "CPU": cpu,
        "Memory": memory_gb,
        "Disks": disk_gb,
        "Portgroups": portgroups,
        "IPs": ip_str,
    }


def get_cluster_vms(service_instance, cluster_name: str) -> list[dict]:
    content = service_instance.RetrieveContent()
    view = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.ClusterComputeResource], True
    )
    try:
        cluster = next((item for item in view.view if item.name == cluster_name), None)
    finally:
        view.Destroy()

    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_name}")

    vm_view = content.viewManager.CreateContainerView(cluster, [vim.VirtualMachine], True)
    try:
        vms = sorted(
            [_collect_vm_info(vm, cluster_name) for vm in vm_view.view if vm.name],
            key=lambda v: v["Hostname"],
        )
    finally:
        vm_view.Destroy()

    return vms


# Columns sourced from vCenter — overwritten on every run
VCENTER_COLUMNS = {"CPU", "Memory", "Disks", "Portgroups", "IPs"}

# Default column order when creating a new file
DEFAULT_FIELDS = [
    "Hostname",
    "Cluster",
    "OS Family",
    "OS Version",
    "Appliance",
    "Notes",
    "CPU",
    "Memory",
    "Disks",
    "IPs",
    "Portgroups",
]


def _load_existing_workbook(output_path: Path) -> dict[str, dict[str, dict]]:
    """Load existing xlsx into {sheet_name: {hostname: row_dict}}."""
    if not output_path.exists():
        return {}
    wb = openpyxl.load_workbook(output_path)
    sheets: dict[str, dict[str, dict]] = {}
    for ws in wb.worksheets:
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        rows: dict[str, dict] = {}
        for excel_row in ws.iter_rows(min_row=2, values_only=True):
            row_dict = dict(zip(headers, excel_row))
            hostname = str(row_dict.get("Hostname") or "").strip()
            if hostname:
                rows[hostname] = {k: ("" if v is None else v) for k, v in row_dict.items()}
        sheets[ws.title] = rows
    return sheets


def _load_csv_baseline(csv_path: Path) -> dict[str, dict[str, dict]]:
    """Seed from CSV: returns {cluster_name: {hostname: row_dict}}."""
    if not csv_path.exists():
        return {}
    sheets: dict[str, dict[str, dict]] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            hostname = (row.get("Hostname") or "").strip()
            cluster = (row.get("Cluster") or "").strip()
            if not hostname:
                continue
            sheets.setdefault(cluster, {})
            sheets[cluster][hostname] = {k: (v or "") for k, v in row.items()}
    return sheets


def _write_sheet(ws, fieldnames: list[str], rows_ordered: list[dict]) -> None:
    """Write header + data rows to a worksheet with a styled header row."""
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="4472C4")

    ws.append(fieldnames)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    for row in rows_ordered:
        ws.append([row.get(col, "") for col in fieldnames])


def upsert_vcenter_xlsx(
    vms: list[dict], cluster_name: str, output_path: Path, csv_seed_path: Path | None = None
) -> None:
    """Upsert vCenter data for one cluster into its own sheet in the workbook."""
    vcenter_index = {vm["Hostname"]: vm for vm in vms}

    # Always start from the CSV as the authoritative baseline for manual columns.
    # Then overlay with any xlsx data so edits made directly in xlsx are preserved.
    csv_sheets: dict[str, dict[str, dict]] = (
        _load_csv_baseline(csv_seed_path) if csv_seed_path else {}
    )
    xlsx_sheets: dict[str, dict[str, dict]] = (
        _load_existing_workbook(output_path) if output_path.exists() else {}
    )

    # Merge: start with csv rows, overlay non-empty xlsx values on top
    merged_sheets: dict[str, dict[str, dict]] = {}
    all_sheet_names = set(csv_sheets) | set(xlsx_sheets)
    for sheet in all_sheet_names:
        csv_rows = csv_sheets.get(sheet, {})
        xlsx_rows = xlsx_sheets.get(sheet, {})
        merged: dict[str, dict] = {}
        for hostname, csv_row in csv_rows.items():
            merged[hostname] = dict(csv_row)
            # Overlay xlsx values if present and non-empty (preserves manual xlsx edits)
            for col, val in xlsx_rows.get(hostname, {}).items():
                if val != "" and val is not None:
                    merged[hostname][col] = val
        # Include any xlsx-only rows (added directly in xlsx, not in CSV)
        for hostname, xlsx_row in xlsx_rows.items():
            if hostname not in merged:
                merged[hostname] = dict(xlsx_row)
        merged_sheets[sheet] = merged

    existing_rows = merged_sheets.get(cluster_name, {})
    fieldnames = DEFAULT_FIELDS[:]

    # Only update vCenter columns for hostnames already in the file;
    # do NOT add new hosts that aren't in the existing data.
    for hostname, row in existing_rows.items():
        if hostname in vcenter_index:
            vcenter_data = vcenter_index[hostname]
            for col in VCENTER_COLUMNS:
                row[col] = vcenter_data.get(col, "")
            row["Cluster"] = cluster_name

    # Preserve existing row order
    ordered_hostnames = list(existing_rows.keys())

    # Rebuild workbook preserving all other sheets
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default empty sheet

    merged_sheets[cluster_name] = existing_rows

    for sheet_name, sheet_rows in merged_sheets.items():
        ws = wb.create_sheet(title=sheet_name)
        order = ordered_hostnames if sheet_name == cluster_name else list(sheet_rows.keys())
        _write_sheet(ws, fieldnames, [sheet_rows[h] for h in order if h in sheet_rows])

    wb.save(output_path)


def update_server_facts(facts_path: Path, vm_names: set[str], cluster_name: str) -> None:
    with facts_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "Hostname" not in fieldnames:
            raise ValueError("server_facts_rcd.csv must contain a Hostname column")
        if "Cluster" not in fieldnames:
            fieldnames.append("Cluster")
        rows = list(reader)

    for row in rows:
        hostname = (row.get("Hostname") or "").strip()
        if hostname in vm_names:
            row["Cluster"] = cluster_name
        else:
            row.setdefault("Cluster", "")

    with facts_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_ssl_context(insecure: bool) -> ssl.SSLContext | None:
    if not insecure:
        return None
    return ssl._create_unverified_context()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect VM names from a vCenter cluster and update server facts."
    )
    parser.add_argument("--vcenter", required=True, help="vCenter hostname or IP")
    parser.add_argument("--cluster", required=True, help="Cluster name to query")
    parser.add_argument(
        "--output",
        default="vcenter_servers_by_cluster.xlsx",
        help="Excel file to upsert VM data into, one sheet per cluster (preserves manual columns)",
    )
    parser.add_argument(
        "--facts-file",
        default="server_facts_rcd.csv",
        help="CSV file to update with Cluster column",
    )
    parser.add_argument(
        "--no-insecure",
        dest="insecure",
        action="store_false",
        help="Enable SSL certificate verification (disabled by default)",
    )
    parser.set_defaults(insecure=True)

    args = parser.parse_args()

    load_env_file(Path("~/.api_variables_env").expanduser())

    username = VAULT_SECRET_PATH.split("/")[-1]
    password = get_vault_password()

    ssl_context = build_ssl_context(args.insecure)
    service_instance = SmartConnect(
        host=args.vcenter,
        user=username,
        pwd=password,
        sslContext=ssl_context,
    )
    try:
        vms = get_cluster_vms(service_instance, args.cluster)
    finally:
        Disconnect(service_instance)

    output_path = Path(args.output)
    csv_seed = Path("vcenter_servers_by_cluster.csv")
    upsert_vcenter_xlsx(vms, args.cluster, output_path, csv_seed_path=csv_seed)

    facts_path = Path(args.facts_file)
    vm_names = {v["Hostname"] for v in vms}
    update_server_facts(facts_path, vm_names, args.cluster)

    print(f"Wrote cluster CSV: {output_path}")
    print(f"Updated server facts: {facts_path}")


if __name__ == "__main__":
    main()
