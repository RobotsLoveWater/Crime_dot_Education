"""Print the cache key for a representative filter-history chain."""

from __future__ import annotations


def main() -> None:
    entries = [
        {"desc": "example", "action": ["f", "time", "gt", "14"]},
        {"desc": "example", "action": ["f", "moc1", "eq", "H"]},
        {"desc": "example", "action": ["f", "moc2", "eq", "1"]},
    ]
    print("/".join(".".join(item["action"]) for item in entries))


if __name__ == "__main__":
    main()
