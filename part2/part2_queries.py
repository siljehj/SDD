import csv
import os
import re
import sys
import time
from math import cos, radians

from tabulate import tabulate


# Make DbConnector.py in ../Files available when this script is placed in part2/
sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "Files"
        )
    )
)

from DbConnector import DbConnector


# GPS points in the Porto dataset are sampled every 15 seconds.
GPS_INTERVAL_SECONDS = 15

# The trip timestamps were stored in Norwegian time when the data was loaded.
# Norway and Portugal change to and from summer time at the same moment,
# so Porto local time is always exactly one hour behind Norwegian time.
PORTO_OFFSET_HOURS = -1

# Number of trips processed per batch when building temporary statistics.
# Batching avoids large InnoDB transactions and lock-table errors.
TRIP_STATS_BATCH_SIZE = 20000

EARTH_RADIUS_M = 6_371_000.0

CITY_HALL_LON = -8.62911
CITY_HALL_LAT = 41.15794

# Keep terminal output readable. Full result sets are always saved as CSV files.
TERMINAL_PREVIEW_ROWS = 20

# Results are stored inside part2/results/.
RESULTS_DIR = os.path.join(
    os.path.dirname(__file__),
    "results"
)


class Tee:
    """Write printed output both to the terminal and to a log file."""

    def __init__(self, terminal, log_file):
        self.terminal = terminal
        self.log_file = log_file

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()


def prepare_results_directory():
    """Create a clean results directory for the current run."""
    os.makedirs(RESULTS_DIR, exist_ok=True)

    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith(".csv") or filename in {
            "run_output.txt",
            "summary.txt"
        }:
            try:
                os.remove(os.path.join(RESULTS_DIR, filename))
            except OSError:
                pass


def result_filename(title):
    """Create a readable file name from a question title."""
    name = title.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name + ".csv"


def haversine_sql(lat1, lon1, lat2, lon2):
    """
    Returns a MySQL expression for the Haversine distance in meters.
    lat1/lon1/lat2/lon2 are SQL expressions, e.g. 'g1.latitude'.
    """
    return f"""
    (
        2 * {EARTH_RADIUS_M} * ASIN(
            SQRT(
                LEAST(
                    1.0,
                    POWER(SIN(RADIANS(({lat2}) - ({lat1})) / 2), 2)
                    +
                    COS(RADIANS({lat1})) * COS(RADIANS({lat2}))
                    * POWER(SIN(RADIANS(({lon2}) - ({lon1})) / 2), 2)
                )
            )
        )
    )
    """


class Part2Program:

    def __init__(self):
        self.connection = DbConnector()
        self.db_connection = self.connection.db_connection
        self.cursor = self.connection.cursor
        self.trip_stats_ready = False
        self.summary_path = os.path.join(RESULTS_DIR, "summary.txt")

    def save_csv(self, title, headers, rows):
        """Save the complete result set for one question."""
        filename = result_filename(title)
        path = os.path.join(RESULTS_DIR, filename)

        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(rows)

        return path

    def append_summary(self, title, rows, headers, elapsed, csv_path):
        """Append a compact record of one result to summary.txt."""
        preview = rows[:TERMINAL_PREVIEW_ROWS]

        with open(self.summary_path, "a", encoding="utf-8") as file:
            file.write("\n" + "=" * 90 + "\n")
            file.write(title + "\n")
            file.write("=" * 90 + "\n")

            if preview:
                file.write(
                    tabulate(
                        preview,
                        headers=headers,
                        tablefmt="github",
                        floatfmt=".2f"
                    )
                )
                file.write("\n")
            else:
                file.write("(No rows returned)\n")

            if len(rows) > len(preview):
                file.write(
                    f"... {len(rows) - len(preview)} additional rows are stored in the CSV file.\n"
                )

            file.write(f"Rows returned: {len(rows)}\n")
            file.write(f"Query time: {elapsed:.2f} s\n")
            file.write(f"Full result: {csv_path}\n")

    def execute_and_print(self, title, query, params=None):
        """
        Execute a SELECT query.

        The terminal only shows a short preview when a result set is large.
        Every row is saved to a CSV file in part2/results/.
        """
        print("\n" + "=" * 90)
        print(title)
        print("=" * 90)

        start = time.time()
        self.cursor.execute(query, params or ())
        rows = self.cursor.fetchall()
        headers = self.cursor.column_names
        elapsed = time.time() - start

        csv_path = self.save_csv(title, headers, rows)

        preview = rows[:TERMINAL_PREVIEW_ROWS]

        if preview:
            print(
                tabulate(
                    preview,
                    headers=headers,
                    tablefmt="github",
                    floatfmt=".2f"
                )
            )
        else:
            print("(No rows returned)")

        if len(rows) > len(preview):
            print(
                f"\n... {len(rows) - len(preview)} additional rows are not shown "
                "in the terminal."
            )

        print(f"\nRows returned: {len(rows)}")
        print(f"Query time: {elapsed:.2f} s")
        print(f"Full result saved to: {csv_path}")

        self.append_summary(
            title=title,
            rows=rows,
            headers=headers,
            elapsed=elapsed,
            csv_path=csv_path
        )

        return rows

    def prepare_trip_stats(self):
        """
        Build one temporary table with values reused by several questions:
        number of GPS points, trip duration, end time, and total distance.

        Duration:
            (number of GPS points - 1) * 15 seconds

        Distance:
            sum of Haversine distances between consecutive GPS points.

        Start and end times are stored in Porto local time.

        The temporary table uses InnoDB and disappears when the connection closes.
        Trips are processed in batches to avoid one very large transaction.
        """
        if self.trip_stats_ready:
            return

        print("\n" + "=" * 90)
        print("Preparing temporary trip statistics")
        print("This is the heaviest step and may take several minutes on the full dataset.")
        print("=" * 90)

        start = time.time()

        self.db_connection.commit()

        self.cursor.execute(
            "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"
        )

        self.cursor.execute("DROP TEMPORARY TABLE IF EXISTS trip_stats")

        print("Creating temporary analytics table...")
        self.cursor.execute("""
            CREATE TEMPORARY TABLE trip_stats (
                trip_id BIGINT NOT NULL PRIMARY KEY,
                taxi_id INT NOT NULL,
                call_type CHAR(1) NOT NULL,
                start_time DATETIME NOT NULL,
                point_count INT NOT NULL,
                first_point_id INT NULL,
                last_point_id INT NULL,
                duration_seconds INT NOT NULL,
                end_time DATETIME NOT NULL,
                distance_m DOUBLE NOT NULL DEFAULT 0,
                INDEX idx_trip_stats_taxi_start (taxi_id, start_time),
                INDEX idx_trip_stats_call_type (call_type),
                INDEX idx_trip_stats_point_count (point_count)
            ) ENGINE=InnoDB
        """)
        self.db_connection.commit()

        segment_distance = haversine_sql(
            "g1.latitude",
            "g1.longitude",
            "g2.latitude",
            "g2.longitude"
        )

        self.cursor.execute("SELECT COUNT(*) FROM trip")
        total_trips = self.cursor.fetchone()[0]

        print(
            f"Calculating statistics for {total_trips:,} trips "
            f"in batches of {TRIP_STATS_BATCH_SIZE:,}..."
        )

        processed = 0
        last_trip_id = -1
        batch_number = 0

        while True:
            # Keyset pagination: find the upper trip_id for the next batch.
            self.cursor.execute(
                """
                SELECT trip_id
                FROM trip
                WHERE trip_id > %s
                ORDER BY trip_id
                LIMIT %s
                """,
                (last_trip_id, TRIP_STATS_BATCH_SIZE)
            )
            batch_ids = self.cursor.fetchall()

            if not batch_ids:
                break

            upper_trip_id = batch_ids[-1][0]
            batch_count = len(batch_ids)

            self.cursor.execute(
                f"""
                INSERT INTO trip_stats (
                    trip_id,
                    taxi_id,
                    call_type,
                    start_time,
                    point_count,
                    first_point_id,
                    last_point_id,
                    duration_seconds,
                    end_time,
                    distance_m
                )
                SELECT
                    t.trip_id,
                    t.taxi_id,
                    t.call_type,
                    TIMESTAMPADD(
                        HOUR, {PORTO_OFFSET_HOURS}, t.timestamp
                    ) AS start_time,
                    COUNT(g1.point_id) AS point_count,
                    MIN(g1.point_id) AS first_point_id,
                    MAX(g1.point_id) AS last_point_id,
                    CASE
                        WHEN COUNT(g1.point_id) = 0 THEN 0
                        ELSE (COUNT(g1.point_id) - 1) * {GPS_INTERVAL_SECONDS}
                    END AS duration_seconds,
                    TIMESTAMPADD(
                        SECOND,
                        CASE
                            WHEN COUNT(g1.point_id) = 0 THEN 0
                            ELSE (COUNT(g1.point_id) - 1) * {GPS_INTERVAL_SECONDS}
                        END,
                        TIMESTAMPADD(HOUR, {PORTO_OFFSET_HOURS}, t.timestamp)
                    ) AS end_time,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN g2.point_id IS NULL THEN 0
                                ELSE {segment_distance}
                            END
                        ),
                        0
                    ) AS distance_m
                FROM trip AS t
                LEFT JOIN gps_point AS g1
                    ON g1.trip_id = t.trip_id
                LEFT JOIN gps_point AS g2
                    ON g2.trip_id = g1.trip_id
                   AND g2.point_id = g1.point_id + 1
                WHERE t.trip_id > %s
                  AND t.trip_id <= %s
                GROUP BY
                    t.trip_id,
                    t.taxi_id,
                    t.call_type,
                    t.timestamp
                """,
                (last_trip_id, upper_trip_id)
            )

            # Commit after every batch so locks are released continuously.
            self.db_connection.commit()

            processed += batch_count
            batch_number += 1
            last_trip_id = upper_trip_id

            if (
                batch_number == 1
                or batch_number % 10 == 0
                or processed == total_trips
            ):
                print(
                    f"Processed {processed:,} / {total_trips:,} trips "
                    f"({100 * processed / total_trips:.1f}%)"
                )

        self.trip_stats_ready = True

        print(
            f"Temporary trip statistics ready in "
            f"{time.time() - start:.2f} s"
        )
        print("No permanent database tables were changed.")

    # ------------------------------------------------------------------
    # Question 1
    # ------------------------------------------------------------------
    def question_1(self):
        query = """
            SELECT
                (SELECT COUNT(*) FROM taxi) AS number_of_taxis,
                (SELECT COUNT(*) FROM trip) AS number_of_trips,
                (SELECT COUNT(*) FROM gps_point) AS number_of_gps_points
        """
        return self.execute_and_print(
            "Question 1: Number of taxis, trips, and GPS points",
            query
        )

    # ------------------------------------------------------------------
    # Question 2
    # ------------------------------------------------------------------
    def question_2(self):
        query = """
            SELECT
                ROUND(AVG(trip_count), 2) AS average_trips_per_taxi
            FROM (
                SELECT
                    tx.taxi_id,
                    COUNT(t.trip_id) AS trip_count
                FROM taxi AS tx
                LEFT JOIN trip AS t
                    ON t.taxi_id = tx.taxi_id
                GROUP BY tx.taxi_id
            ) AS trips_per_taxi
        """
        return self.execute_and_print(
            "Question 2: Average number of trips per taxi",
            query
        )

    # ------------------------------------------------------------------
    # Question 3
    # ------------------------------------------------------------------
    def question_3(self):
        query = """
            SELECT
                taxi_id,
                COUNT(*) AS number_of_trips
            FROM trip
            GROUP BY taxi_id
            ORDER BY number_of_trips DESC, taxi_id
            LIMIT 20
        """
        return self.execute_and_print(
            "Question 3: Top 20 taxis with the most trips",
            query
        )

    # ------------------------------------------------------------------
    # Question 4a
    # ------------------------------------------------------------------
    def question_4a(self):
        # RANK keeps ties. GROUP_CONCAT combines tied call types
        # so that each taxi appears on exactly one row.
        query = """
            WITH call_type_counts AS (
                SELECT
                    taxi_id,
                    call_type,
                    COUNT(*) AS trip_count
                FROM trip
                GROUP BY taxi_id, call_type
            ),
            ranked AS (
                SELECT
                    taxi_id,
                    call_type,
                    trip_count,
                    RANK() OVER (
                        PARTITION BY taxi_id
                        ORDER BY trip_count DESC
                    ) AS rnk
                FROM call_type_counts
            ),
            top_call_types AS (
                SELECT
                    taxi_id,
                    GROUP_CONCAT(
                        call_type
                        ORDER BY call_type
                        SEPARATOR ','
                    ) AS most_used_call_type,
                    MAX(trip_count) AS trip_count
                FROM ranked
                WHERE rnk = 1
                GROUP BY taxi_id
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY taxi_id) AS row_no,
                taxi_id,
                most_used_call_type,
                trip_count
            FROM top_call_types
            ORDER BY taxi_id
        """
        return self.execute_and_print(
            "Question 4a: Most used call type per taxi",
            query
        )


    # ------------------------------------------------------------------
    # Question 4a - Part 2
    # ------------------------------------------------------------------
    def question_4a_summary(self):
        query = """
            WITH call_type_counts AS (
                SELECT
                    taxi_id,
                    call_type,
                    COUNT(*) AS trip_count
                FROM trip
                GROUP BY taxi_id, call_type
            ),
            ranked AS (
                SELECT
                    taxi_id,
                    call_type,
                    trip_count,
                    RANK() OVER (
                        PARTITION BY taxi_id
                        ORDER BY trip_count DESC
                    ) AS rnk
                FROM call_type_counts
            ),
            top_call_types AS (
                SELECT
                    taxi_id,
                    GROUP_CONCAT(
                        call_type
                        ORDER BY call_type
                        SEPARATOR ','
                    ) AS most_used_call_type
                FROM ranked
                WHERE rnk = 1
                GROUP BY taxi_id
            )
            SELECT
                most_used_call_type,
                COUNT(*) AS number_of_taxis,
                ROUND(
                    100.0 * COUNT(*) /
                    (SELECT COUNT(*) FROM top_call_types),
                    2
                ) AS share_of_taxis_pct
            FROM top_call_types
            GROUP BY most_used_call_type
            ORDER BY number_of_taxis DESC, most_used_call_type
        """
        return self.execute_and_print(
            "Question 4a part 2: Number of taxis by most used call type",
            query
        )


    # ------------------------------------------------------------------
    # Question 4b
    # ------------------------------------------------------------------
    def question_4b(self):
        self.prepare_trip_stats()

        query = """
            SELECT
                call_type,
                COUNT(*) AS number_of_trips,
                ROUND(AVG(duration_seconds) / 60, 2) AS avg_duration_minutes,
                ROUND(AVG(distance_m) / 1000, 2) AS avg_distance_km,

                ROUND(
                    100.0 * SUM(
                        CASE WHEN HOUR(start_time) >= 0
                                  AND HOUR(start_time) < 6
                             THEN 1 ELSE 0 END
                    ) / COUNT(*),
                    2
                ) AS share_00_06_pct,

                ROUND(
                    100.0 * SUM(
                        CASE WHEN HOUR(start_time) >= 6
                                  AND HOUR(start_time) < 12
                             THEN 1 ELSE 0 END
                    ) / COUNT(*),
                    2
                ) AS share_06_12_pct,

                ROUND(
                    100.0 * SUM(
                        CASE WHEN HOUR(start_time) >= 12
                                  AND HOUR(start_time) < 18
                             THEN 1 ELSE 0 END
                    ) / COUNT(*),
                    2
                ) AS share_12_18_pct,

                ROUND(
                    100.0 * SUM(
                        CASE WHEN HOUR(start_time) >= 18
                                  AND HOUR(start_time) < 24
                             THEN 1 ELSE 0 END
                    ) / COUNT(*),
                    2
                ) AS share_18_24_pct

            FROM trip_stats
            GROUP BY call_type
            ORDER BY call_type
        """
        return self.execute_and_print(
            "Question 4b: Duration, distance, and start-time shares by call type",
            query
        )

    # ------------------------------------------------------------------
    # Question 5
    # ------------------------------------------------------------------
    def question_5(self):
        self.prepare_trip_stats()

        query = """
            SELECT
                taxi_id,
                COUNT(*) AS number_of_trips,
                ROUND(SUM(duration_seconds) / 3600, 2) AS total_hours,
                ROUND(SUM(distance_m) / 1000, 2) AS total_distance_km
            FROM trip_stats
            GROUP BY taxi_id
            ORDER BY total_hours DESC, total_distance_km DESC, taxi_id
        """
        return self.execute_and_print(
            "Question 5: Taxis ordered by total hours driven",
            query
        )

    # ------------------------------------------------------------------
    # Question 6
    # ------------------------------------------------------------------
    def question_6(self):
        radius_m = 100.0

        box_m = radius_m * 1.1
        lat_delta = box_m / 111_320.0
        lon_delta = box_m / (
            111_320.0 * cos(radians(CITY_HALL_LAT))
        )

        city_distance = haversine_sql(
            "g.latitude",
            "g.longitude",
            str(CITY_HALL_LAT),
            str(CITY_HALL_LON)
        )

        query = f"""
            SELECT
                g.trip_id,
                ROUND(MIN({city_distance}), 2) AS closest_distance_m
            FROM gps_point AS g
            WHERE g.latitude BETWEEN {CITY_HALL_LAT - lat_delta}
                                 AND {CITY_HALL_LAT + lat_delta}
              AND g.longitude BETWEEN {CITY_HALL_LON - lon_delta}
                                  AND {CITY_HALL_LON + lon_delta}
            GROUP BY g.trip_id
            HAVING MIN({city_distance}) <= {radius_m}
            ORDER BY closest_distance_m ASC, g.trip_id
        """
        return self.execute_and_print(
            "Question 6: Trips that passed within 100 m of Porto City Hall",
            query
        )

    # ------------------------------------------------------------------
    # Question 7
    # ------------------------------------------------------------------
    def question_7(self):
        query = """
            WITH gps_counts AS (
                SELECT
                    t.trip_id,
                    COUNT(g.point_id) AS point_count
                FROM trip AS t
                LEFT JOIN gps_point AS g
                    ON g.trip_id = t.trip_id
                GROUP BY t.trip_id
            ),
            invalid_breakdown AS (
                SELECT
                    point_count,
                    COUNT(*) AS number_of_trips
                FROM gps_counts
                WHERE point_count < 3
                GROUP BY point_count
            ),
            all_invalid_categories AS (
                SELECT 0 AS point_count
                UNION ALL
                SELECT 1
                UNION ALL
                SELECT 2
            )
            SELECT
                CAST(c.point_count AS CHAR) AS gps_points,
                COALESCE(b.number_of_trips, 0) AS number_of_invalid_trips
            FROM all_invalid_categories AS c
            LEFT JOIN invalid_breakdown AS b
                ON b.point_count = c.point_count

            UNION ALL

            SELECT
                'TOTAL' AS gps_points,
                SUM(
                    CASE
                        WHEN gc.point_count < 3 THEN 1
                        ELSE 0
                    END
                ) AS number_of_invalid_trips
            FROM gps_counts AS gc
        """
        return self.execute_and_print(
            "Question 7: Invalid trips by number of GPS points",
            query
        )


    # ------------------------------------------------------------------
    # Question 8
    # ------------------------------------------------------------------
    def question_8(self):
        self.prepare_trip_stats()

        # Detailed list of trips that start on one calendar day
        # and end exactly on the next calendar day.
        detail_query = """
            SELECT
                trip_id,
                taxi_id,
                start_time,
                end_time,
                ROUND(duration_seconds / 60, 2) AS duration_minutes
            FROM trip_stats
            WHERE DATE(end_time) = DATE_ADD(DATE(start_time), INTERVAL 1 DAY)
            ORDER BY start_time, trip_id
        """

        rows = self.execute_and_print(
            "Question 8: Trips crossing midnight",
            detail_query
        )

        # Separate summary so the total number is clearly visible
        # and saved in its own CSV file.
        count_query = """
            SELECT
                COUNT(*) AS number_of_trips_crossing_midnight
            FROM trip_stats
            WHERE DATE(end_time) = DATE_ADD(DATE(start_time), INTERVAL 1 DAY)
        """

        self.execute_and_print(
            "Question 8 summary: Total number of trips crossing midnight",
            count_query
        )

        return rows


    # ------------------------------------------------------------------
    # Question 9
    # ------------------------------------------------------------------
    def question_9(self):
        self.prepare_trip_stats()

        endpoint_distance = haversine_sql(
            "start_point.latitude",
            "start_point.longitude",
            "end_point.latitude",
            "end_point.longitude"
        )

        # Detailed list of trips whose start and end points
        # are within 50 metres of each other.
        # total_distance_km is included so we can distinguish truly short
        # trips from trips that travelled farther and returned near the start.
        detail_query = f"""
            WITH endpoint_distances AS (
                SELECT
                    ts.trip_id,
                    ts.taxi_id,
                    ts.distance_m AS total_distance_m,
                    {endpoint_distance} AS start_end_distance_m
                FROM trip_stats AS ts
                JOIN gps_point AS start_point
                    ON start_point.trip_id = ts.trip_id
                   AND start_point.point_id = ts.first_point_id
                JOIN gps_point AS end_point
                    ON end_point.trip_id = ts.trip_id
                   AND end_point.point_id = ts.last_point_id
            )
            SELECT
                trip_id,
                taxi_id,
                ROUND(start_end_distance_m, 2) AS start_end_distance_m,
                ROUND(total_distance_m / 1000, 3) AS total_distance_km
            FROM endpoint_distances
            WHERE start_end_distance_m <= 50
        """

        rows = self.execute_and_print(
            "Question 9: Circular trips (start and end within 50 m)",
            detail_query
        )

        summary_query = f"""
            WITH endpoint_distances AS (
                SELECT
                    ts.trip_id,
                    ts.distance_m AS total_distance_m,
                    {endpoint_distance} AS start_end_distance_m
                FROM trip_stats AS ts
                JOIN gps_point AS start_point
                    ON start_point.trip_id = ts.trip_id
                   AND start_point.point_id = ts.first_point_id
                JOIN gps_point AS end_point
                    ON end_point.trip_id = ts.trip_id
                   AND end_point.point_id = ts.last_point_id
            ),
            circular_trips AS (
                SELECT
                    trip_id,
                    total_distance_m
                FROM endpoint_distances
                WHERE start_end_distance_m <= 50
            )
            SELECT
                COUNT(*) AS total_circular_trips,
                SUM(CASE WHEN total_distance_m < 100 THEN 1 ELSE 0 END)
                    AS total_distance_under_100m,
                SUM(CASE WHEN total_distance_m >= 100 THEN 1 ELSE 0 END)
                    AS total_distance_over_0_1km,
                SUM(CASE WHEN total_distance_m > 1000 THEN 1 ELSE 0 END)
                    AS total_distance_over_1km
            FROM circular_trips
        """

        self.execute_and_print(
            "Question 9 summary: Circular-trip distance breakdown",
            summary_query
        )

        return rows


    # ------------------------------------------------------------------
    # Question 10
    # ------------------------------------------------------------------
    def question_10(self):
        self.prepare_trip_stats()

        query = """
            WITH ordered_trips AS (
                SELECT
                    trip_id,
                    taxi_id,
                    start_time,
                    end_time,
                    LAG(end_time) OVER (
                        PARTITION BY taxi_id
                        ORDER BY start_time, trip_id
                    ) AS previous_end_time
                FROM trip_stats
            ),
            idle_times AS (
                SELECT
                    taxi_id,
                    TIMESTAMPDIFF(
                        SECOND,
                        previous_end_time,
                        start_time
                    ) AS idle_seconds
                FROM ordered_trips
                WHERE previous_end_time IS NOT NULL
                  AND start_time >= previous_end_time
            )
            SELECT
                taxi_id,
                COUNT(*) AS number_of_idle_periods,
                ROUND(AVG(idle_seconds) / 60, 2) AS avg_idle_minutes,
                ROUND(AVG(idle_seconds) / 3600, 2) AS avg_idle_hours
            FROM idle_times
            GROUP BY taxi_id
            ORDER BY AVG(idle_seconds) DESC, taxi_id
            LIMIT 20
        """
        return self.execute_and_print(
            "Question 10: Top 20 taxis with highest average idle time",
            query
        )


def main():
    prepare_results_directory()

    original_stdout = sys.stdout
    run_log_path = os.path.join(RESULTS_DIR, "run_output.txt")
    run_log = open(run_log_path, "w", encoding="utf-8")
    sys.stdout = Tee(original_stdout, run_log)

    program = None

    try:
        print("Part 2 analysis")
        print(f"Results directory: {RESULTS_DIR}")
        print(
            f"Large result sets show only the first {TERMINAL_PREVIEW_ROWS} rows "
            "in the terminal."
        )
        print("Complete results are saved as CSV files.\n")

        program = Part2Program()

        program.question_1()
        program.question_2()
        program.question_3()
        program.question_4a()
        program.question_4a_summary()

        # The temporary trip_stats table is created the first time
        # one of the trajectory-based questions needs it, then reused.
        program.question_4b()
        program.question_5()
        program.question_6()
        program.question_7()
        program.question_8()
        program.question_9()
        program.question_10()

        print("\n" + "=" * 90)
        print("ALL QUESTIONS FINISHED")
        print("=" * 90)
        print(f"Terminal log: {run_log_path}")
        print(f"Compact summary: {os.path.join(RESULTS_DIR, 'summary.txt')}")
        print(f"Full CSV results: {RESULTS_DIR}")

    except Exception as e:
        print("\nERROR:", e)
        print(
            "The output up to the error is still saved in "
            f"{run_log_path}"
        )

    finally:
        if program:
            program.connection.close_connection()

        sys.stdout.flush()
        sys.stdout = original_stdout
        run_log.close()


if __name__ == "__main__":
    main()