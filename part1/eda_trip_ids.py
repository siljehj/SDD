import csv
import json
import math
from collections import defaultdict
from datetime import datetime


FILE = "./files/porto.csv"

# Connected-trip criterion
MAX_START_DISTANCE_M = 500

# New diagnostic criterion
CONSECUTIVE_POINT_DISTANCE_M = 100


# ============================================================
# Helper functions
# ============================================================

def format_timestamp(timestamp):
    """Convert Unix timestamp to readable date/time."""

    return datetime.fromtimestamp(
        int(timestamp)
    ).strftime("%d %b %Y, %H:%M:%S")


def haversine_distance_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km."""

    R = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * R * math.asin(math.sqrt(a))


def parse_polyline(value):
    """
    Convert POLYLINE JSON string into a list of
    (longitude, latitude) tuples.
    """

    if not value:
        return []

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def trajectories_identical(traj1, traj2):
    """Check whether two trajectories are exactly identical."""

    return traj1 == traj2


def trajectory_is_subset(shorter, longer):
    """
    Check whether the shorter trajectory occurs
    consecutively inside the longer trajectory.
    """

    if len(shorter) > len(longer):
        return False

    n = len(shorter)

    for i in range(len(longer) - n + 1):

        if longer[i:i + n] == shorter:
            return True

    return False


def start_distance_km(traj1, traj2):
    """Calculate distance between the starting points."""

    if not traj1 or not traj2:
        return None

    lon1, lat1 = traj1[0]
    lon2, lat2 = traj2[0]

    return haversine_distance_km(
        lat1,
        lon1,
        lat2,
        lon2
    )


def find_close_consecutive_points(
    short_traj,
    long_traj,
    threshold_m
):
    """
    For every point in the short trajectory, check whether
    there are two consecutive points in the long trajectory
    where BOTH points are within the given distance threshold.

    Returns matches containing:

        short point index
        long point indices
        distance from short point to each long point
    """

    matches = []

    threshold_km = threshold_m / 1000

    for short_index, short_point in enumerate(short_traj):

        short_lon, short_lat = short_point

        for long_index in range(len(long_traj) - 1):

            point_a = long_traj[long_index]
            point_b = long_traj[long_index + 1]

            lon_a, lat_a = point_a
            lon_b, lat_b = point_b

            distance_a = haversine_distance_km(
                short_lat,
                short_lon,
                lat_a,
                lon_a
            )

            distance_b = haversine_distance_km(
                short_lat,
                short_lon,
                lat_b,
                lon_b
            )

            if (
                distance_a <= threshold_km
                and distance_b <= threshold_km
            ):

                matches.append(
                    {
                        "short_index": short_index,
                        "long_index_1": long_index,
                        "long_index_2": long_index + 1,
                        "distance_1_m": distance_a * 1000,
                        "distance_2_m": distance_b * 1000
                    }
                )

    return matches


# ============================================================
# Find duplicated trip IDs
# ============================================================

print("Reading data...")

trip_counts = defaultdict(int)

with open(
    FILE,
    "r",
    encoding="utf-8",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:
        trip_counts[row["TRIP_ID"]] += 1


duplicate_ids = {
    trip_id
    for trip_id, count in trip_counts.items()
    if count > 1
}

print(
    f"Found {len(duplicate_ids)} duplicated trip IDs."
)


# ============================================================
# Read only duplicated trips
# ============================================================

duplicate_rows = defaultdict(list)

with open(
    FILE,
    "r",
    encoding="utf-8",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        trip_id = row["TRIP_ID"]

        if trip_id in duplicate_ids:
            duplicate_rows[trip_id].append(row)


# ============================================================
# Investigation
# ============================================================

print()
print("Duplicate trip ID investigation")
print("--------------------------------")
print(
    f"Total duplicated trip IDs: "
    f"{len(duplicate_ids)}"
)


# ============================================================
# 1. Remove duplicated IDs containing MISSING_DATA
# ============================================================

duplicate_ids_with_missing_data = set()

for trip_id in duplicate_ids:

    rows = duplicate_rows[trip_id]

    if any(
        row["MISSING_DATA"] == "True"
        for row in rows
    ):
        duplicate_ids_with_missing_data.add(trip_id)


remaining_ids = (
    set(duplicate_ids)
    - duplicate_ids_with_missing_data
)


# ============================================================
# 2. Exactly identical rows
# ============================================================

exact_duplicates = []

for trip_id in remaining_ids:

    rows = duplicate_rows[trip_id]

    if len(rows) < 2:
        continue

    first = rows[0]

    for other in rows[1:]:

        if first == other:
            exact_duplicates.append(trip_id)
            break


remaining_ids -= set(exact_duplicates)


# ============================================================
# 3. Parse trajectories
# ============================================================

parsed = {}

for trip_id in remaining_ids:

    rows = duplicate_rows[trip_id]

    parsed[trip_id] = []

    for row in rows:

        trajectory = parse_polyline(
            row["POLYLINE"]
        )

        parsed[trip_id].append(
            {
                "row": row,
                "trajectory": trajectory,
                "timestamp": int(row["TIMESTAMP"])
            }
        )


# ============================================================
# Classification containers
# ============================================================

identical_trajectories = []
subset_trajectories = []
connected_trips = []
one_point_trips = []
unexplained = []


# ============================================================
# Compare each duplicated trip ID internally
# ============================================================

for trip_id in remaining_ids:

    entries = parsed[trip_id]

    if len(entries) < 2:
        unexplained.append(trip_id)
        continue

    found = False

    for i in range(len(entries)):

        for j in range(i + 1, len(entries)):

            first = entries[i]
            second = entries[j]

            traj1 = first["trajectory"]
            traj2 = second["trajectory"]

            # ------------------------------------------------
            # Identical trajectories
            # ------------------------------------------------

            if trajectories_identical(
                traj1,
                traj2
            ):

                identical_trajectories.append(
                    (
                        trip_id,
                        first,
                        second
                    )
                )

                found = True
                break

            # ------------------------------------------------
            # One trajectory is a subset of the other
            # ------------------------------------------------

            if (
                len(traj1) <= len(traj2)
                and trajectory_is_subset(
                    traj1,
                    traj2
                )
            ) or (
                len(traj2) <= len(traj1)
                and trajectory_is_subset(
                    traj2,
                    traj1
                )
            ):

                subset_trajectories.append(
                    (
                        trip_id,
                        first,
                        second
                    )
                )

                found = True
                break

            # ------------------------------------------------
            # Connected trajectories
            # ------------------------------------------------

            if first["timestamp"] == second["timestamp"]:

                distance_km = start_distance_km(
                    traj1,
                    traj2
                )

                if (
                    distance_km is not None
                    and distance_km * 1000
                    <= MAX_START_DISTANCE_M
                ):

                    connected_trips.append(
                        (
                            trip_id,
                            first,
                            second,
                            distance_km
                        )
                    )

                    found = True
                    break

        if found:
            break

    if not found:

        # ----------------------------------------------------
        # 4. Trajectories with only 1 point
        # ----------------------------------------------------

        if (
            len(entries[0]["trajectory"]) == 1
            or len(entries[1]["trajectory"]) == 1
        ):

            one_point_trips.append(trip_id)

        else:

            unexplained.append(trip_id)


# ============================================================
# Funnel
# ============================================================

print()
print("Funnel")
print("------")

print(
    f"Initial duplicated trip IDs: "
    f"{len(duplicate_ids)}"
)

print(
    f"Containing MISSING_DATA: "
    f"{len(duplicate_ids_with_missing_data)}"
)

remaining = (
    len(duplicate_ids)
    - len(duplicate_ids_with_missing_data)
)

print(
    f"Remaining: {remaining}"
)

print(
    f"Exactly identical rows: "
    f"{len(exact_duplicates)}"
)

remaining -= len(exact_duplicates)

print(
    f"Remaining: {remaining}"
)

print(
    f"Identical trajectories: "
    f"{len(identical_trajectories)}"
)

remaining -= len(identical_trajectories)

print(
    f"Remaining: {remaining}"
)

print(
    f"One trajectory is a subset of the other: "
    f"{len(subset_trajectories)}"
)

remaining -= len(subset_trajectories)

print(
    f"Remaining: {remaining}"
)

print(
    f"Trajectories connected within spatial tolerance: "
    f"{len(connected_trips)}"
)

remaining -= len(connected_trips)

print(
    f"Remaining: {remaining}"
)

print(
    f"Trajectories with only 1 point: "
    f"{len(one_point_trips)}"
)

remaining -= len(one_point_trips)

print(
    f"Remaining unexplained: {remaining}"
)


# ============================================================
# Connection criteria
# ============================================================

print()
print("Connection criteria")
print("-------------------")

print(
    f"Maximum start-point distance: "
    f"{MAX_START_DISTANCE_M:g} m"
)

print(
    "Start timestamps must be identical."
)


# ============================================================
# Unexplained duplicate trips
# ============================================================

print()
print("Unexplained duplicate trips")
print("---------------------------")

for trip_id in unexplained:

    entries = parsed[trip_id]

    if len(entries) < 2:
        continue

    first = entries[0]
    second = entries[1]

    traj1 = first["trajectory"]
    traj2 = second["trajectory"]

    same_start_time = (
        first["timestamp"]
        == second["timestamp"]
    )

    distance_km = start_distance_km(
        traj1,
        traj2
    )

    call_types = [
        first["row"]["CALL_TYPE"],
        second["row"]["CALL_TYPE"]
    ]

    origin_calls = [
        first["row"]["ORIGIN_CALL"],
        second["row"]["ORIGIN_CALL"]
    ]

    origin_stands = [
        first["row"]["ORIGIN_STAND"],
        second["row"]["ORIGIN_STAND"]
    ]

    print(
        f"{trip_id} | "
        f"CALL_TYPE: {call_types} | "
        f"Points: "
        f"[{len(traj1)}, {len(traj2)}] | "
        f"Start time: "
        f"{format_timestamp(first['timestamp'])} | "
        f"Same start time: {same_start_time} | "
        f"Start point distance: "
        f"{distance_km * 1000:.1f} m | "
        f"ORIGIN_CALL: {origin_calls} | "
        f"ORIGIN_STAND: {origin_stands}"
    )


# ============================================================
# New diagnostic:
# Check whether short trajectory points are close to
# TWO CONSECUTIVE points in the longer trajectory
# ============================================================

print()
print("Consecutive-point diagnostic")
print("----------------------------")

print(
    f"Distance threshold: "
    f"{CONSECUTIVE_POINT_DISTANCE_M:g} m"
)

print(
    "Each point in the shorter trajectory is checked "
    "against every pair of consecutive points in the "
    "longer trajectory."
)

for trip_id in unexplained:

    entries = parsed[trip_id]

    if len(entries) < 2:
        continue

    first = entries[0]
    second = entries[1]

    traj1 = first["trajectory"]
    traj2 = second["trajectory"]

    # Determine which is the short and long trajectory.
    if len(traj1) <= len(traj2):

        short_entry = first
        long_entry = second

        short_label = "Trip 1"
        long_label = "Trip 2"

    else:

        short_entry = second
        long_entry = first

        short_label = "Trip 2"
        long_label = "Trip 1"

    short_traj = short_entry["trajectory"]
    long_traj = long_entry["trajectory"]

    matches = find_close_consecutive_points(
        short_traj,
        long_traj,
        CONSECUTIVE_POINT_DISTANCE_M
    )

    print()
    print(trip_id)

    print(
        f"{short_label}: "
        f"{len(short_traj)} points"
    )

    print(
        f"{long_label}: "
        f"{len(long_traj)} points"
    )

    if not matches:

        print(
            "No short-trajectory points were found "
            "within 100 m of two consecutive points "
            "in the longer trajectory."
        )

    else:

        for match in matches:

            print(
                f"Short point "
                f"{match['short_index'] + 1} -> "
                f"Long points "
                f"{match['long_index_1'] + 1} and "
                f"{match['long_index_2'] + 1} | "
                f"Distances: "
                f"{match['distance_1_m']:.1f} m, "
                f"{match['distance_2_m']:.1f} m"
            )


# ============================================================
# Final check
# ============================================================

print()
print("Final check")
print("-----------")

classified = (
    len(duplicate_ids_with_missing_data)
    + len(exact_duplicates)
    + len(identical_trajectories)
    + len(subset_trajectories)
    + len(connected_trips)
    + len(one_point_trips)
    + len(unexplained)
)

print(
    f"Original duplicated trip IDs: "
    f"{len(duplicate_ids)}"
)

print(
    f"Classified trip IDs: "
    f"{classified}"
)

if classified == len(duplicate_ids):

    print(
        "All duplicated trip IDs accounted for."
    )

else:

    print(
        f"WARNING: "
        f"{len(duplicate_ids) - classified} "
        f"trip IDs were not accounted for."
    )