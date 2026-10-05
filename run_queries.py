"""Run q1.rq, q2.rq, and q3.rq against the Wikidata Query Service."""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "mkr1/1.0",
}
QUERY_FILES = ("q1.rq", "q2.rq", "q3.rq")


def execute_query(query: str, attempts: int = 3) -> dict:
    """Execute a SPARQL query, retrying temporary endpoint failures."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                ENDPOINT,
                data={"query": query},
                headers=HEADERS,
                timeout=120,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Query retry loop ended unexpectedly")


def write_csv(result: dict, output_path: Path) -> int:
    columns = result["head"]["vars"]
    bindings = result["results"]["bindings"]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for binding in bindings:
            writer.writerow(
                {column: binding.get(column, {}).get("value", "") for column in columns}
            )
    return len(bindings)


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    row_counts = {}
    for query_name in QUERY_FILES:
        query_path = project_dir / query_name
        result = execute_query(query_path.read_text(encoding="utf-8"))
        output_path = query_path.with_suffix(".csv")
        row_counts[output_path.name] = write_csv(result, output_path)
        print(f"{output_path.name}: {row_counts[output_path.name]} rows")

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {"retrieved_at": retrieved_at}
    (project_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"meta.json: {retrieved_at}")


if __name__ == "__main__":
    main()
