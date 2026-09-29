import csv
import json
import heapq
from collections import Counter

import matplotlib.pyplot as plt
from haversine import haversine
from tabulate import tabulate
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent
FILE = SCRIPT_DIR / "files" / "porto.csv"


# ============================================================
# Helper functions
# ============================================================

def parse_polyline(value):
    if not value:
        return []

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def valid_coordinate(point):
    if not isinstance(point, list) or len(point) != 2:
        return False

    try:
        longitude = float(point[0])
        latitude = float(point[1])
    except (TypeError, ValueError):
        return False

    return (
        -180 <= longitude <= 180
        and -90 <= latitude <= 90
    )


def weighted_mean(frequency):
    total = sum(frequency.values())

    if total == 0:
        return 0

    return sum(
        value * count
        for value, count in frequency.items()
    ) / total


def weighted_median(frequency):
    total = sum(frequency.values())

    if total == 0:
        return 0

    middle_1 = (total + 1) // 2
    middle_2 = (total + 2) // 2

    cumulative = 0
    median_1 = None
    median_2 = None

    for value in sorted(frequency):

        cumulative += frequency[value]

        if median_1 is None and cumulative >= middle_1:
            median_1 = value

        if cumulative >= middle_2:
            median_2 = value
            break

    return (median_1 + median_2) / 2


# ============================================================
# Configuration
# ============================================================

SPEED_THRESHOLD_KMH = 150


# ============================================================
# Counters and dictionaries
# ============================================================

trajectory_length_counts = Counter()

missing_data_lengths = {
    "True": Counter(),
    "False": Counter()
}

speed_buckets = {
    "0-20": 0,
    "20-40": 0,
    "40-60": 0,
    "60-80": 0,
    "80-100": 0,
    "100-120": 0,
    "120-150": 0,
    "150-200": 0,
    "200+": 0
}

# TRIP_ID -> (number of violations, total movements)
trip_speed_violations = {}

missing_data_count = 0
complete_data_count = 0

empty_polylines = 0
malformed_polylines = 0

invalid_coordinate_points = 0
invalid_coordinate_trips = 0

speed_violations = 0
trips_with_speed_violations = 0
max_speed_kmh = 0


# ============================================================
# Read dataset once
# ============================================================

print("Reading data...")

with open(
    FILE,
    "r",
    encoding="utf-8",
    newline=""
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        trajectory = parse_polyline(row["POLYLINE"])

        # ----------------------------------------------------
        # POLYLINE validity
        # ----------------------------------------------------

        if trajectory is None:

            malformed_polylines += 1
            continue

        if len(trajectory) == 0:
            empty_polylines += 1

        # ----------------------------------------------------
        # Trajectory length
        # ----------------------------------------------------

        number_of_points = len(trajectory)

        trajectory_length_counts[
            number_of_points
        ] += 1

        # ----------------------------------------------------
        # MISSING_DATA
        # ----------------------------------------------------

        missing_status = row["MISSING_DATA"]

        missing_data_lengths[
            missing_status
        ][number_of_points] += 1

        if missing_status == "True":
            missing_data_count += 1
        else:
            complete_data_count += 1

        # ----------------------------------------------------
        # Coordinate validity
        # ----------------------------------------------------

        trip_has_invalid_coordinate = False

        for point in trajectory:

            if not valid_coordinate(point):

                invalid_coordinate_points += 1
                trip_has_invalid_coordinate = True

        if trip_has_invalid_coordinate:
            invalid_coordinate_trips += 1

        # ----------------------------------------------------
        # Implied speed
        # ----------------------------------------------------

        if len(trajectory) >= 2:

            trip_violations = 0
            total_movements = len(trajectory) - 1

            for i in range(total_movements):

                lon1, lat1 = trajectory[i]
                lon2, lat2 = trajectory[i + 1]

                distance_km = haversine(
                    (lat1, lon1),
                    (lat2, lon2)
                )

                # GPS points are 15 seconds apart.
                speed_kmh = distance_km * 240

                if speed_kmh > max_speed_kmh:
                    max_speed_kmh = speed_kmh

                # ------------------------------------------------
                # Threshold
                # ------------------------------------------------

                if speed_kmh > SPEED_THRESHOLD_KMH:

                    speed_violations += 1
                    trip_violations += 1

                # ------------------------------------------------
                # Speed distribution
                # ------------------------------------------------

                if speed_kmh < 20:
                    speed_buckets["0-20"] += 1

                elif speed_kmh < 40:
                    speed_buckets["20-40"] += 1

                elif speed_kmh < 60:
                    speed_buckets["40-60"] += 1

                elif speed_kmh < 80:
                    speed_buckets["60-80"] += 1

                elif speed_kmh < 100:
                    speed_buckets["80-100"] += 1

                elif speed_kmh < 120:
                    speed_buckets["100-120"] += 1

                elif speed_kmh < 150:
                    speed_buckets["120-150"] += 1

                elif speed_kmh < 200:
                    speed_buckets["150-200"] += 1

                else:
                    speed_buckets["200+"] += 1

            if trip_violations > 0:
                trips_with_speed_violations += 1

            trip_speed_violations[
                row["TRIP_ID"]
            ] = (
                trip_violations,
                total_movements
            )


# ============================================================
# Trajectory overview
# ============================================================

print()
print("Trajectory overview")
print("-------------------")

total_trips = sum(
    trajectory_length_counts.values()
)

print(
    "Total trips analyzed:",
    total_trips
)

print(
    "Minimum number of points:",
    min(trajectory_length_counts)
)

print(
    "Maximum number of points:",
    max(trajectory_length_counts)
)

print(
    "Average number of points:",
    f"{weighted_mean(trajectory_length_counts):.2f}"
)

print(
    "Median number of points:",
    weighted_median(trajectory_length_counts)
)


# ============================================================
# Trajectory length distribution
# ============================================================

print()
print("Trajectory length distribution")
print("------------------------------")

length_buckets = {
    "0": 0,
    "1": 0,
    "2": 0,
    "3-10": 0,
    "11-50": 0,
    "51-100": 0,
    "101-500": 0,
    "501+": 0
}

for length, count in trajectory_length_counts.items():

    if length == 0:
        length_buckets["0"] += count

    elif length == 1:
        length_buckets["1"] += count

    elif length == 2:
        length_buckets["2"] += count

    elif length <= 10:
        length_buckets["3-10"] += count

    elif length <= 50:
        length_buckets["11-50"] += count

    elif length <= 100:
        length_buckets["51-100"] += count

    elif length <= 500:
        length_buckets["101-500"] += count

    else:
        length_buckets["501+"] += count


print(
    tabulate(
        length_buckets.items(),
        headers=[
            "Number of GPS points",
            "Number of trips"
        ],
        tablefmt="pretty"
    )
)


# ============================================================
# Trajectory length distribution graph
# ============================================================

print()
print("Creating trajectory length distribution graph...")

plt.figure()

plt.bar(
    length_buckets.keys(),
    length_buckets.values(),
    color="darkorange"
)

plt.xlabel("Number of GPS points")
plt.ylabel("Number of trips")
plt.title("Distribution of Trajectory Lengths")

plt.show()


# ============================================================
# MISSING_DATA impact
# ============================================================

print()
print("MISSING_DATA impact")
print("-------------------")

print(
    tabulate(
        {
            "MISSING_DATA = False": complete_data_count,
            "MISSING_DATA = True": missing_data_count
        }.items(),
        headers=[
            "MISSING_DATA",
            "Number of trips"
        ],
        tablefmt="pretty"
    )
)

if missing_data_count > 0:

    missing_lengths = missing_data_lengths["True"]

    print()
    print(
        "Trajectory lengths for MISSING_DATA = True"
    )

    print(
        "Minimum:",
        min(missing_lengths)
    )

    print(
        "Maximum:",
        max(missing_lengths)
    )

    print(
        "Average:",
        f"{weighted_mean(missing_lengths):.2f}"
    )

    print(
        "Median:",
        weighted_median(missing_lengths)
    )


# ============================================================
# POLYLINE validity
# ============================================================

print()
print("POLYLINE validity")
print("-----------------")

print(
    tabulate(
        {
            "Empty POLYLINE": empty_polylines,
            "Malformed POLYLINE": malformed_polylines,
            "Trips with invalid coordinates":
                invalid_coordinate_trips,
            "Invalid coordinate points":
                invalid_coordinate_points
        }.items(),
        headers=[
            "Check",
            "Count"
        ],
        tablefmt="pretty"
    )
)


# ============================================================
# Implied speed results
# ============================================================

print()
print("Implied speed between GPS points")
print("---------------------------------")

print(
    f"Speed threshold: "
    f"{SPEED_THRESHOLD_KMH} km/h"
)

print(
    f"Point-to-point movements above threshold: "
    f"{speed_violations}"
)

print(
    f"Trips containing at least one violation: "
    f"{trips_with_speed_violations}"
)

print(
    f"Maximum implied speed: "
    f"{max_speed_kmh:.1f} km/h"
)


# ============================================================
# Implied speed distribution
# ============================================================

print()
print("Implied speed distribution")
print("---------------------------")

print(
    tabulate(
        speed_buckets.items(),
        headers=[
            "Implied speed (km/h)",
            "Number of movements"
        ],
        tablefmt="pretty"
    )
)


# ============================================================
# Implied speed distribution graph
# ============================================================

print()
print("Creating implied speed distribution graph...")

plt.figure()

plt.bar(
    speed_buckets.keys(),
    speed_buckets.values(),
    color="darkorange"
)

plt.xlabel("Implied speed (km/h)")
plt.ylabel("Number of point-to-point movements")
plt.title("Distribution of Implied Speeds")

plt.show()


# ============================================================
# 150+ km/h movements by trajectory length
# ============================================================

print()
print("150+ km/h movements by trajectory length")
print("-----------------------------------------")

speed_by_length = {
    "2": {"total": 0, "violations": 0},
    "3-10": {"total": 0, "violations": 0},
    "11-50": {"total": 0, "violations": 0},
    "51-100": {"total": 0, "violations": 0},
    "101-500": {"total": 0, "violations": 0},
    "501+": {"total": 0, "violations": 0}
}

for trip_id, (violations, movements) in trip_speed_violations.items():

    points = movements + 1

    if points == 2:
        bucket = "2"
    elif points <= 10:
        bucket = "3-10"
    elif points <= 50:
        bucket = "11-50"
    elif points <= 100:
        bucket = "51-100"
    elif points <= 500:
        bucket = "101-500"
    else:
        bucket = "501+"

    speed_by_length[bucket]["total"] += 1

    if violations > 0:
        speed_by_length[bucket]["violations"] += 1


print(
    tabulate(
        (
            [
                bucket,
                values["total"],
                values["violations"],
                f"{values['violations'] / values['total'] * 100:.1f}%"
                if values["total"] > 0 else "0.0%"
            ]
            for bucket, values in speed_by_length.items()
        ),
        headers=[
            "GPS points",
            "Total trips",
            "Trips with 150+ km/h",
            "Percentage"
        ],
        tablefmt="pretty"
    )
)


# ============================================================
# Distribution of percentage of movements above 150 km/h
# ============================================================

print()
print("Distribution of trips by percentage of 150+ km/h movements")
print("------------------------------------------------------------")

speed_percentage_buckets = {
    "0%": 0,
    ">0-5%": 0,
    ">5-10%": 0,
    ">10-25%": 0,
    ">25-50%": 0,
    ">50-75%": 0,
    ">75-99%": 0,
    "100%": 0
}

for trip_id, (violations, movements) in trip_speed_violations.items():

    if movements == 0:
        continue

    percentage = violations / movements * 100

    if percentage == 0:
        bucket = "0%"
    elif percentage <= 5:
        bucket = ">0-5%"
    elif percentage <= 10:
        bucket = ">5-10%"
    elif percentage <= 25:
        bucket = ">10-25%"
    elif percentage <= 50:
        bucket = ">25-50%"
    elif percentage <= 75:
        bucket = ">50-75%"
    elif percentage < 100:
        bucket = ">75-99%"
    else:
        bucket = "100%"

    speed_percentage_buckets[bucket] += 1


print(
    tabulate(
        speed_percentage_buckets.items(),
        headers=[
            "Percentage of movements above 150 km/h",
            "Number of trips"
        ],
        tablefmt="pretty"
    )
)


# ============================================================
# Graph: percentage of movements above 150 km/h
# ============================================================

print()
print("Creating 150+ km/h percentage distribution graph...")

plt.figure()

plt.bar(
    speed_percentage_buckets.keys(),
    speed_percentage_buckets.values(),
    color="darkorange"
)

plt.xlabel("Percentage of movements above 150 km/h")
plt.ylabel("Number of trips")
plt.title("Distribution of Trips by High-Speed Movements")

plt.xticks(rotation=45)

plt.tight_layout()
plt.show()


# ============================================================
# Finish
# ============================================================

print()
print("EDA trajectories finished.")