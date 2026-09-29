import csv
from collections import Counter
from datetime import datetime
import json

from tabulate import tabulate
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent
FILE = SCRIPT_DIR / "files" / "porto.csv"


# ============================================================
# Load dataset
# ============================================================

print("Reading data...")

with open(FILE, "r", encoding="utf-8", newline="") as file:
    reader = csv.DictReader(file)
    data = list(reader)
    columns = reader.fieldnames

print("Data loaded.")


# ============================================================
# Dataset overview
# ============================================================

print("\nDataset overview")
print("----------------")

print("Number of rows:", len(data))
print("Number of columns:", len(columns))

print("\nColumns")
print("-------")

for column in columns:
    print("-", column)


# ============================================================
# Missing values
# ============================================================

print("\nMissing values")
print("--------------")

missing = {}

for column in columns:
    missing[column] = sum(
        1
        for row in data
        if row[column] == ""
    )

missing_table = [
    [column, count]
    for column, count in missing.items()
]

print(
    tabulate(
        missing_table,
        headers=["Column", "Missing values"],
        tablefmt="pretty"
    )
)


# ============================================================
# ID overview
# ============================================================

print("\nID overview")
print("-----------")

trip_id_counts = Counter(
    row["TRIP_ID"]
    for row in data
)

taxi_ids = {
    row["TAXI_ID"]
    for row in data
}

unique_trip_ids = len(trip_id_counts)
unique_taxi_ids = len(taxi_ids)

duplicate_trip_ids = sum(
    1
    for count in trip_id_counts.values()
    if count > 1
)

print("Unique TRIP_IDs:", unique_trip_ids)
print("Unique TAXI_IDs:", unique_taxi_ids)
print("Duplicated TRIP_IDs:", duplicate_trip_ids)


# ============================================================
# CALL_TYPE
# ============================================================

print("\nCALL_TYPE")
print("---------")

call_type_counts = Counter(
    row["CALL_TYPE"]
    for row in data
)

call_type_table = [
    [call_type, count]
    for call_type, count
    in sorted(call_type_counts.items())
]

print(
    tabulate(
        call_type_table,
        headers=["CALL_TYPE", "Count"],
        tablefmt="pretty"
    )
)


# ============================================================
# CALL_TYPE consistency
# ============================================================

print("\nCALL_TYPE consistency")
print("--------------------")

a_without_origin_call = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "A"
    and row["ORIGIN_CALL"] == ""
)

b_without_origin_stand = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "B"
    and row["ORIGIN_STAND"] == ""
)

c_with_origin_call = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "C"
    and row["ORIGIN_CALL"] != ""
)

c_with_origin_stand = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "C"
    and row["ORIGIN_STAND"] != ""
)

a_with_origin_stand = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "A"
    and row["ORIGIN_STAND"] != ""
)

b_with_origin_call = sum(
    1
    for row in data
    if row["CALL_TYPE"] == "B"
    and row["ORIGIN_CALL"] != ""
)

call_type_consistency_table = [
    ["A without ORIGIN_CALL", a_without_origin_call],
    ["B without ORIGIN_STAND", b_without_origin_stand],
    ["C with ORIGIN_CALL", c_with_origin_call],
    ["C with ORIGIN_STAND", c_with_origin_stand],
    ["A with ORIGIN_STAND", a_with_origin_stand],
    ["B with ORIGIN_CALL", b_with_origin_call],
]

print(
    tabulate(
        call_type_consistency_table,
        headers=["Check", "Count"],
        tablefmt="pretty"
    )
)


# ============================================================
# B trips without ORIGIN_STAND
# ============================================================

print("\nB trips without ORIGIN_STAND")
print("---------------------------")

b_missing_stand = [
    row
    for row in data
    if row["CALL_TYPE"] == "B"
    and row["ORIGIN_STAND"] == ""
]

b_missing_taxis = {
    row["TAXI_ID"]
    for row in b_missing_stand
}

b_missing_timestamps = [
    int(row["TIMESTAMP"])
    for row in b_missing_stand
]

print("Number of trips:", len(b_missing_stand))
print("Distinct taxis:", len(b_missing_taxis))

if b_missing_timestamps:
    print(
        "Time range:",
        datetime.fromtimestamp(min(b_missing_timestamps)),
        "-",
        datetime.fromtimestamp(max(b_missing_timestamps))
    )

b_short_trajectories = 0

for row in b_missing_stand:

    try:
        trajectory = json.loads(row["POLYLINE"])
        number_of_points = len(trajectory)

    except (json.JSONDecodeError, TypeError):
        number_of_points = 0

    if number_of_points < 3:
        b_short_trajectories += 1

print(
    "Trips with fewer than 3 GPS points:",
    b_short_trajectories
)


# ============================================================
# Examples of B trips without ORIGIN_STAND
# ============================================================

print()
print("Examples of B trips without ORIGIN_STAND")
print("-----------------------------------------")

example_count = 10

for row in b_missing_stand[:example_count]:

    try:
        trajectory = json.loads(row["POLYLINE"])
        number_of_points = len(trajectory)

    except (json.JSONDecodeError, TypeError):
        number_of_points = 0

    print(
        f"TRIP_ID: {row['TRIP_ID']} | "
        f"TAXI_ID: {row['TAXI_ID']} | "
        f"TIMESTAMP: {row['TIMESTAMP']} | "
        f"ORIGIN_CALL: {row['ORIGIN_CALL']} | "
        f"ORIGIN_STAND: {row['ORIGIN_STAND']} | "
        f"MISSING_DATA: {row['MISSING_DATA']} | "
        f"POLYLINE points: {number_of_points}"
    )


# ============================================================
# DAY_TYPE
# ============================================================

print("\nDAY_TYPE")
print("--------")

day_type_counts = Counter(
    row["DAY_TYPE"]
    for row in data
)

day_type_table = [
    [day_type, count]
    for day_type, count
    in sorted(day_type_counts.items())
]

print(
    tabulate(
        day_type_table,
        headers=["DAY_TYPE", "Count"],
        tablefmt="pretty"
    )
)


# ============================================================
# MISSING_DATA
# ============================================================

print("\nMISSING_DATA")
print("------------")

missing_data_counts = Counter(
    row["MISSING_DATA"]
    for row in data
)

missing_data_table = [
    [value, count]
    for value, count
    in sorted(missing_data_counts.items())
]

print(
    tabulate(
        missing_data_table,
        headers=["MISSING_DATA", "Count"],
        tablefmt="pretty"
    )
)


# ============================================================
# Timestamp range
# ============================================================

print("\nTimestamp range")
print("---------------")

timestamps = [
    int(row["TIMESTAMP"])
    for row in data
    if row["TIMESTAMP"] != ""
]

if timestamps:

    earliest = min(timestamps)
    latest = max(timestamps)

    print(
        "Earliest trip:",
        datetime.fromtimestamp(earliest)
    )

    print(
        "Latest trip:",
        datetime.fromtimestamp(latest)
    )


# ============================================================
# Finish
# ============================================================

print("\nEDA overview finished.")