import csv
import json
from pathlib import Path

from haversine import haversine


# ============================================================
# File paths
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = SCRIPT_DIR / "files" / "porto.csv"
OUTPUT_FILE = SCRIPT_DIR / "part1" / "porto_cleaned.csv"


# ============================================================
# Cleaning parameters
# ============================================================

SPEED_THRESHOLD_KMH = 150
SPEED_PERCENTAGE_THRESHOLD = 50
START_POINT_DISTANCE_THRESHOLD_KM = 0.5


# ============================================================
# Helper functions
# ============================================================

def parse_polyline(value):
    """Convert POLYLINE JSON string into GPS points."""

    if not value:
        return []

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def implied_speed_kmh(point1, point2):
    """Calculate implied speed between two GPS points.

    GPS points are recorded 15 seconds apart.
    """

    lon1, lat1 = point1
    lon2, lat2 = point2

    distance_km = haversine(
        (lat1, lon1),
        (lat2, lon2)
    )

    return distance_km * 240


def speed_violation_percentage(trajectory):
    """Calculate percentage of movements above 150 km/h."""

    movements = len(trajectory) - 1

    if movements <= 0:
        return 0

    violations = 0

    for i in range(movements):

        speed = implied_speed_kmh(
            trajectory[i],
            trajectory[i + 1]
        )

        if speed > SPEED_THRESHOLD_KMH:
            violations += 1

    return violations / movements * 100


def origin_information_score(row):
    """
    Score the completeness of the relevant origin information.

    A trips:
        ORIGIN_CALL is relevant.

    B trips:
        ORIGIN_STAND is relevant.

    C trips:
        Neither origin field is expected.
    """

    call_type = row["CALL_TYPE"]

    if call_type == "A":
        return int(row["ORIGIN_CALL"] != "")

    if call_type == "B":
        return int(row["ORIGIN_STAND"] != "")

    return 0


def start_points_distance_km(trajectory1, trajectory2):
    """Calculate distance between the starting points."""

    if not trajectory1 or not trajectory2:
        return None

    lon1, lat1 = trajectory1[0]
    lon2, lat2 = trajectory2[0]

    return haversine(
        (lat1, lon1),
        (lat2, lon2)
    )


# ============================================================
# Read dataset
# ============================================================

print("Reading data...")
print()

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8",
    newline=""
) as file:

    reader = csv.DictReader(file)

    rows = []

    for row in reader:

        # ----------------------------------------------------
        # Remove DAY_TYPE immediately
        # ----------------------------------------------------

        row.pop("DAY_TYPE", None)

        rows.append(row)


original_rows = len(rows)

print("Rows loaded:", original_rows)


# ============================================================
# Step 1: Remove MISSING_DATA = True
# ============================================================

print()
print("Step 1: Removing MISSING_DATA = True")

before = len(rows)

rows = [
    row
    for row in rows
    if row["MISSING_DATA"] != "True"
]

removed_missing_data = before - len(rows)

print("Removed:", removed_missing_data)


# ============================================================
# Step 2: Remove 0- and 1-point trajectories
# ============================================================

print()
print("Step 2: Removing 0- and 1-point trajectories")

valid_rows = []
removed_short_trajectories = 0

for row in rows:

    trajectory = parse_polyline(row["POLYLINE"])

    if trajectory is None or len(trajectory) < 2:

        removed_short_trajectories += 1

    else:

        valid_rows.append(row)


rows = valid_rows

print("Removed:", removed_short_trajectories)


# ============================================================
# Step 3: Group rows by TRIP_ID
# ============================================================

print()
print("Step 3: Investigating duplicate TRIP_IDs")

trip_groups = {}

for row in rows:

    trip_id = row["TRIP_ID"]

    if trip_id not in trip_groups:
        trip_groups[trip_id] = []

    trip_groups[trip_id].append(row)


duplicate_groups = {
    trip_id: group
    for trip_id, group in trip_groups.items()
    if len(group) > 1
}

print("Unique trips:", len(trip_groups))
print("Duplicate TRIP_IDs:", len(duplicate_groups))


# ============================================================
# Step 4: Handle duplicate TRIP_IDs
# ============================================================

print()
print("Step 4: Handling duplicate TRIP_IDs")

cleaned_rows = []

duplicate_identical_rows = 0
duplicate_identical_trajectories = 0
duplicate_subsets = 0
duplicate_connected = 0
duplicate_one_point = 0
duplicate_unexplained = 0


for trip_id, group in trip_groups.items():

    # --------------------------------------------------------
    # No duplicate
    # --------------------------------------------------------

    if len(group) == 1:

        cleaned_rows.append(group[0])
        continue


    # --------------------------------------------------------
    # Prepare trajectory information
    # --------------------------------------------------------

    trajectory_data = []

    for row in group:

        trajectory = parse_polyline(row["POLYLINE"])

        trajectory_data.append(
            {
                "row": row,
                "trajectory": trajectory,
                "points": len(trajectory)
            }
        )


    # --------------------------------------------------------
    # Case 1: Exactly identical rows
    # --------------------------------------------------------

    if all(
        group[0][column] == row[column]
        for row in group[1:]
        for column in group[0]
    ):

        cleaned_rows.append(group[0])
        duplicate_identical_rows += 1

        continue


    # --------------------------------------------------------
    # Case 2: Identical trajectories
    # --------------------------------------------------------

    first_trajectory = trajectory_data[0]["trajectory"]

    identical_trajectory = all(
        item["trajectory"] == first_trajectory
        for item in trajectory_data[1:]
    )

    if identical_trajectory:

        best = max(
            trajectory_data,
            key=lambda item: origin_information_score(
                item["row"]
            )
        )

        cleaned_rows.append(best["row"])
        duplicate_identical_trajectories += 1

        continue


    # --------------------------------------------------------
    # Case 3: One trajectory is a subset of another
    # --------------------------------------------------------

    subset_found = False

    for i in range(len(trajectory_data)):

        for j in range(len(trajectory_data)):

            if i == j:
                continue

            trajectory_i = trajectory_data[i]["trajectory"]
            trajectory_j = trajectory_data[j]["trajectory"]

            if len(trajectory_i) >= len(trajectory_j):
                continue

            if trajectory_i == trajectory_j[:len(trajectory_i)]:

                best = trajectory_data[j]

                cleaned_rows.append(best["row"])
                duplicate_subsets += 1

                subset_found = True

                break

        if subset_found:
            break

    if subset_found:
        continue


    # --------------------------------------------------------
    # Case 4: Connected trajectories
    #
    # Same timestamp and starting points within 500 m.
    # Keep the trajectory with the most GPS points.
    # --------------------------------------------------------

    connected_found = False

    for i in range(len(trajectory_data)):

        for j in range(i + 1, len(trajectory_data)):

            row_i = trajectory_data[i]["row"]
            row_j = trajectory_data[j]["row"]

            if row_i["TIMESTAMP"] != row_j["TIMESTAMP"]:
                continue

            distance = start_points_distance_km(
                trajectory_data[i]["trajectory"],
                trajectory_data[j]["trajectory"]
            )

            if (
                distance is not None
                and distance <= START_POINT_DISTANCE_THRESHOLD_KM
            ):

                best = max(
                    trajectory_data[i],
                    trajectory_data[j],
                    key=lambda item: item["points"]
                )

                cleaned_rows.append(best["row"])
                duplicate_connected += 1

                connected_found = True

                break

        if connected_found:
            break

    if connected_found:
        continue


    # --------------------------------------------------------
    # Case 5: One trajectory has only 1 point
    #
    # Normally already removed in Step 2.
    # --------------------------------------------------------

    one_point = [
        item
        for item in trajectory_data
        if item["points"] == 1
    ]

    if one_point:

        best = max(
            trajectory_data,
            key=lambda item: item["points"]
        )

        cleaned_rows.append(best["row"])
        duplicate_one_point += 1

        continue


    # --------------------------------------------------------
    # Case 6: Unexplained duplicate
    #
    # Keep trajectory with most GPS points.
    # --------------------------------------------------------

    best = max(
        trajectory_data,
        key=lambda item: item["points"]
    )

    cleaned_rows.append(best["row"])
    duplicate_unexplained += 1


rows = cleaned_rows


# ============================================================
# Check rows after duplicate handling
# ============================================================

print()
print("Rows after duplicate handling:", len(rows))


# ============================================================
# Duplicate summary
# ============================================================

print()
print("Duplicate handling summary")
print("---------------------------")

print("Exactly identical rows:", duplicate_identical_rows)
print("Identical trajectories:", duplicate_identical_trajectories)
print("Subset trajectories:", duplicate_subsets)
print("Connected trajectories:", duplicate_connected)
print("One-point trajectories:", duplicate_one_point)
print("Unexplained duplicates:", duplicate_unexplained)


# ============================================================
# Step 5: Remove unrealistic trajectories
# ============================================================

print()
print("Step 5: Removing unrealistic trajectories")

cleaned_rows_after_speed = []

removed_speed_anomalies = 0

for row in rows:

    trajectory = parse_polyline(row["POLYLINE"])

    percentage = speed_violation_percentage(
        trajectory
    )

    if percentage > SPEED_PERCENTAGE_THRESHOLD:

        removed_speed_anomalies += 1

    else:

        cleaned_rows_after_speed.append(row)


rows = cleaned_rows_after_speed

print("Removed:", removed_speed_anomalies)


# ============================================================
# Save cleaned dataset
# ============================================================

print()
print("Saving cleaned dataset...")

fieldnames = [
    "TRIP_ID",
    "CALL_TYPE",
    "ORIGIN_CALL",
    "ORIGIN_STAND",
    "TAXI_ID",
    "TIMESTAMP",
    "MISSING_DATA",
    "POLYLINE"
]


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
    newline=""
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(rows)


# ============================================================
# Final summary
# ============================================================

print()
print("Cleaning summary")
print("----------------")

print("Original rows:", original_rows)

print(
    "Removed MISSING_DATA = True:",
    removed_missing_data
)

print(
    "Removed short trajectories:",
    removed_short_trajectories
)

print(
    "Rows after duplicate handling:",
    len(rows) + removed_speed_anomalies
)

print(
    "Removed due to speed:",
    removed_speed_anomalies
)

print(
    "Final rows:",
    len(rows)
)

print(
    "Final unique TRIP_IDs:",
    len({
        row["TRIP_ID"]
        for row in rows
    })
)

print("DAY_TYPE removed: yes")

print()
print(
    "Cleaned dataset saved to:",
    OUTPUT_FILE
)

print()
print("Cleaning finished.")