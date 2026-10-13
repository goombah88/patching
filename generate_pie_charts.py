import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt


def read_column_counts(csv_path: Path, column_name: str) -> Counter:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if column_name not in reader.fieldnames:
            raise ValueError(f"Missing column: {column_name}")
        return Counter(row[column_name].strip() for row in reader if row.get(column_name))


def save_pie_chart(counts: Counter, title: str, output_path: Path) -> None:
    labels = list(counts.keys())
    values = list(counts.values())

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.axis("equal")
    ax.set_title(title)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def main() -> None:
    csv_path = Path("server_facts_both.csv")
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    os_family_counts = read_column_counts(csv_path, "OS Family")
    os_version_counts = read_column_counts(csv_path, "OS Version")

    save_pie_chart(os_family_counts, "OS Family Distribution", Path("os_family_pie.png"))
    save_pie_chart(os_version_counts, "OS Version Distribution", Path("os_version_pie.png"))


if __name__ == "__main__":
    main()
