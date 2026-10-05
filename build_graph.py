"""Build an RDF graph describing flights from a generated CSV file."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, XSD


EX = Namespace("http://example.org/mkr/")


def resource(kind: str, value: str):
    """Return an ex: URI, replacing spaces as required by the assignment."""
    local_name = value.strip().replace(" ", "_")
    return EX[f"{kind}/{quote(local_name, safe='_-')}"]


def normalize_date(value: str) -> str:
    value = value.strip()
    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unsupported departure date: {value!r}")


def read_flights(csv_path: Path) -> list[dict[str, str]]:
    """Read and normalize rows, keeping one row per normalized flight ID."""
    flights: dict[str, dict[str, str]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {
            "flight_id",
            "airline",
            "from_city",
            "from_country",
            "to_city",
            "to_country",
            "dep_date",
            "duration_min",
            "price_eur",
            "note",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")

        for line_number, raw in enumerate(reader, start=2):
            flight_id = raw["flight_id"].strip().upper()
            if not flight_id:
                raise ValueError(f"Empty flight_id on CSV line {line_number}")
            row = {key: (value or "").strip() for key, value in raw.items()}
            row.update(
                flight_id=flight_id,
                airline=row["airline"].strip(),
                from_city=row["from_city"].title(),
                to_city=row["to_city"].title(),
                from_country=row["from_country"].title(),
                to_country=row["to_country"].title(),
                dep_date=normalize_date(row["dep_date"]),
            )
            flights.setdefault(flight_id, row)
    return list(flights.values())


def add_schema(graph: Graph) -> None:
    classes = (EX.Flight, EX.BudgetFlight, EX.LongFlight, EX.Airline, EX.City, EX.Country)
    for class_uri in classes:
        graph.add((class_uri, RDF.type, RDFS.Class))
    graph.add((EX.BudgetFlight, RDFS.subClassOf, EX.Flight))
    graph.add((EX.LongFlight, RDFS.subClassOf, EX.Flight))

    properties = {
        EX.operatedBy: (RDF.Property, EX.Flight, EX.Airline),
        EX.departsFrom: (RDF.Property, EX.Flight, EX.City),
        EX.arrivesAt: (RDF.Property, EX.Flight, EX.City),
        EX.locatedIn: (RDF.Property, EX.City, EX.Country),
        EX.departureDate: (RDF.Property, EX.Flight, XSD.date),
        EX.durationMin: (RDF.Property, EX.Flight, XSD.integer),
        EX.priceEur: (RDF.Property, EX.Flight, XSD.decimal),
        EX.hasDelayMinutes: (RDF.Property, EX.Flight, XSD.integer),
        EX.reportedBy: (RDF.Property, RDF.Statement, RDFS.Resource),
        EX.fromBusyCountry: (RDF.Property, EX.Flight, XSD.boolean),
    }
    for prop, (prop_type, domain, range_) in properties.items():
        graph.add((prop, RDF.type, prop_type))
        graph.add((prop, RDFS.domain, domain))
        graph.add((prop, RDFS.range, range_))


def add_labeled_entity(graph: Graph, uri, class_uri, label: str) -> None:
    graph.add((uri, RDF.type, class_uri))
    graph.add((uri, RDFS.label, Literal(label, lang="en")))


def build_graph(flights: list[dict[str, str]], params: dict[str, object]) -> Graph:
    graph = Graph()
    graph.bind("ex", EX)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)
    add_schema(graph)

    budget_threshold = Decimal(str(params["budget_threshold_eur"]))
    long_flight_min = int(params["long_flight_min"])
    departure_counts = Counter(row["from_country"] for row in flights)

    for row in flights:
        flight = resource("flight", row["flight_id"])
        airline = resource("airline", row["airline"])
        from_city = resource("city", row["from_city"])
        to_city = resource("city", row["to_city"])
        from_country = resource("country", row["from_country"])
        to_country = resource("country", row["to_country"])

        add_labeled_entity(graph, airline, EX.Airline, row["airline"])
        add_labeled_entity(graph, from_city, EX.City, row["from_city"])
        add_labeled_entity(graph, to_city, EX.City, row["to_city"])
        add_labeled_entity(graph, from_country, EX.Country, row["from_country"])
        add_labeled_entity(graph, to_country, EX.Country, row["to_country"])
        graph.add((from_city, EX.locatedIn, from_country))
        graph.add((to_city, EX.locatedIn, to_country))

        graph.add((flight, EX.operatedBy, airline))
        graph.add((flight, EX.departsFrom, from_city))
        graph.add((flight, EX.arrivesAt, to_city))
        graph.add((flight, EX.departureDate, Literal(row["dep_date"], datatype=XSD.date)))
        graph.add((flight, EX.durationMin, Literal(int(row["duration_min"]), datatype=XSD.integer)))

        flight_types = []
        if row["price_eur"]:
            try:
                price = Decimal(row["price_eur"])
            except InvalidOperation as error:
                raise ValueError(f"Invalid price for {row['flight_id']}: {row['price_eur']!r}") from error
            graph.add((flight, EX.priceEur, Literal(price, datatype=XSD.decimal)))
            if price <= budget_threshold:
                flight_types.append(EX.BudgetFlight)
        if int(row["duration_min"]) >= long_flight_min:
            flight_types.append(EX.LongFlight)
        for flight_type in flight_types or [EX.Flight]:
            graph.add((flight, RDF.type, flight_type))

        if departure_counts[row["from_country"]] >= 2:
            graph.add((flight, EX.fromBusyCountry, Literal(True, datatype=XSD.boolean)))

        if row["note"]:
            match = re.fullmatch(r"delay=(\d+);by=([^;]+)", row["note"])
            if not match:
                raise ValueError(f"Invalid delay note for {row['flight_id']}: {row['note']!r}")
            delay_minutes, source_name = match.groups()
            statement = resource("stmt", f"{row['flight_id']}-delay")
            source = resource("source", source_name)
            graph.add((statement, RDF.type, RDF.Statement))
            graph.add((statement, RDF.subject, flight))
            graph.add((statement, RDF.predicate, EX.hasDelayMinutes))
            graph.add((statement, RDF.object, Literal(int(delay_minutes), datatype=XSD.integer)))
            graph.add((statement, EX.reportedBy, source))

    return graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("params_path", type=Path)
    parser.add_argument("output_path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.params_path.open(encoding="utf-8") as stream:
        params = json.load(stream)
    graph = build_graph(read_flights(args.csv_path), params)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=args.output_path, format="turtle")
    print(f"{args.output_path}: {len(graph)} triples")


if __name__ == "__main__":
    main()
