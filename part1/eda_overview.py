import csv
from collections import Counter
from datetime import datetime

from tabulate import tabulate


FILE = "files/porto.csv"


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

duplicate_trip_rows = sum(
    count - 1
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