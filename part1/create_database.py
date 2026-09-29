import csv
import json
import os
import subprocess
import sys
from datetime import datetime


# ============================================================
# Make DbConnector.py available
# ============================================================

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "files"
        )
    )
)

from DbConnector import DbConnector


# ============================================================
# File paths
# ============================================================

CLEANED_FILE = os.path.join(
    os.path.dirname(__file__),
    "porto_cleaned.csv"
)

SQL_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "files",
        "fake_taxi.sql"
    )
)


# ============================================================
# Database settings
# ============================================================

DATABASE_NAME = "fake_taxi"
DOCKER_CONTAINER = "fake-taxi-db"

# Number of trips processed at a time
BATCH_SIZE = 1000


# ============================================================
# Helper functions
# ============================================================

def parse_polyline(value):
    """Convert POLYLINE JSON string into a list of GPS points."""

    if not value:
        return []

    try:
        return json.loads(value)

    except (json.JSONDecodeError, TypeError):
        return []


def convert_timestamp(value):
    """Convert Unix timestamp to MySQL DATETIME."""

    return datetime.fromtimestamp(
        int(value)
    ).strftime("%Y-%m-%d %H:%M:%S")


def convert_optional_int(value):
    """Convert an optional integer to int or None."""

    if value == "":
        return None

    return int(value)


# ============================================================
# Database class
# ============================================================

class PortoDatabase:

    def __init__(self):

        self.connection = DbConnector()

        self.db_connection = (
            self.connection.db_connection
        )

        self.cursor = self.connection.cursor


    # ========================================================
    # Reset tables
    # ========================================================

    def reset_tables(self):

        print()
        print("Resetting database tables...")

        # gps_point must be dropped first because it has
        # a foreign key to trip.

        self.cursor.execute(
            "DROP TABLE IF EXISTS gps_point"
        )

        self.cursor.execute(
            "DROP TABLE IF EXISTS trip"
        )

        self.cursor.execute(
            "DROP TABLE IF EXISTS taxi"
        )

        # Remove the example table from the starter database.

        self.cursor.execute(
            "DROP TABLE IF EXISTS Example"
        )

        self.db_connection.commit()

        print("Existing tables removed.")


    # ========================================================
    # Create tables
    # ========================================================

    def create_tables(self):

        print()
        print("Creating tables...")

        # ----------------------------------------------------
        # Taxi
        # ----------------------------------------------------

        self.cursor.execute("""
            CREATE TABLE taxi (
                taxi_id INT NOT NULL PRIMARY KEY
            )
        """)

        print("Created table: taxi")


        # ----------------------------------------------------
        # Trip
        # ----------------------------------------------------

        self.cursor.execute("""
            CREATE TABLE trip (
                trip_id BIGINT NOT NULL PRIMARY KEY,
                taxi_id INT NOT NULL,
                call_type CHAR(1) NOT NULL,
                origin_call INT,
                origin_stand INT,
                timestamp DATETIME NOT NULL,

                FOREIGN KEY (taxi_id)
                    REFERENCES taxi(taxi_id)
                    ON DELETE RESTRICT
                    ON UPDATE CASCADE
            )
        """)

        print("Created table: trip")


        # ----------------------------------------------------
        # GPS point
        # ----------------------------------------------------

        self.cursor.execute("""
            CREATE TABLE gps_point (
                trip_id BIGINT NOT NULL,
                point_id INT NOT NULL,
                latitude DECIMAL(9,6) NOT NULL,
                longitude DECIMAL(9,6) NOT NULL,

                PRIMARY KEY (trip_id, point_id),

                FOREIGN KEY (trip_id)
                    REFERENCES trip(trip_id)
                    ON DELETE CASCADE
                    ON UPDATE CASCADE
            )
        """)

        print("Created table: gps_point")

        self.db_connection.commit()


    # ========================================================
    # Insert taxis
    # ========================================================

    def insert_taxis(self):

        print()
        print("Finding unique taxis...")

        taxi_ids = set()

        with open(
            CLEANED_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                taxi_ids.add(
                    int(row["TAXI_ID"])
                )


        taxi_rows = [
            (taxi_id,)
            for taxi_id in taxi_ids
        ]

        print(
            f"Unique taxis found: {len(taxi_rows):,}"
        )

        self.cursor.executemany(
            """
            INSERT INTO taxi (taxi_id)
            VALUES (%s)
            """,
            taxi_rows
        )

        self.db_connection.commit()

        print("Taxis inserted.")


    # ========================================================
    # Insert trips and GPS points
    # ========================================================

    def insert_trips_and_gps(self):

        print()
        print("Reading cleaned data...")
        print(
            f"Processing {BATCH_SIZE:,} trips at a time..."
        )

        trip_rows = []
        gps_rows = []

        total_trips = 0
        total_gps_points = 0

        with open(
            CLEANED_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                trip_id = int(
                    row["TRIP_ID"]
                )

                taxi_id = int(
                    row["TAXI_ID"]
                )


                # ------------------------------------------------
                # Add trip
                # ------------------------------------------------

                trip_rows.append(
                    (
                        trip_id,
                        taxi_id,
                        row["CALL_TYPE"],
                        convert_optional_int(
                            row["ORIGIN_CALL"]
                        ),
                        convert_optional_int(
                            row["ORIGIN_STAND"]
                        ),
                        convert_timestamp(
                            row["TIMESTAMP"]
                        )
                    )
                )


                # ------------------------------------------------
                # Add GPS points
                # ------------------------------------------------

                trajectory = parse_polyline(
                    row["POLYLINE"]
                )

                for point_id, point in enumerate(
                    trajectory
                ):

                    longitude = float(
                        point[0]
                    )

                    latitude = float(
                        point[1]
                    )

                    gps_rows.append(
                        (
                            trip_id,
                            point_id,
                            latitude,
                            longitude
                        )
                    )

                    total_gps_points += 1


                total_trips += 1


                # ------------------------------------------------
                # Process batch
                # ------------------------------------------------

                if len(trip_rows) >= BATCH_SIZE:

                    self.insert_batch(
                        trip_rows,
                        gps_rows
                    )

                    trip_rows.clear()
                    gps_rows.clear()

                    print(
                        f"Trips inserted: "
                        f"{total_trips:,}"
                    )


        # --------------------------------------------------------
        # Insert final batch
        # --------------------------------------------------------

        if trip_rows:

            self.insert_batch(
                trip_rows,
                gps_rows
            )

            print(
                f"Trips inserted: "
                f"{total_trips:,}"
            )


        print()
        print("Data insertion finished.")

        print(
            f"Trips inserted: "
            f"{total_trips:,}"
        )

        print(
            f"GPS points inserted: "
            f"{total_gps_points:,}"
        )


    # ========================================================
    # Insert one batch
    # ========================================================

    def insert_batch(
        self,
        trip_rows,
        gps_rows
    ):

        try:

            # ------------------------------------------------
            # Insert trips first
            # ------------------------------------------------

            self.cursor.executemany(
                """
                INSERT INTO trip (
                    trip_id,
                    taxi_id,
                    call_type,
                    origin_call,
                    origin_stand,
                    timestamp
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                trip_rows
            )


            # ------------------------------------------------
            # Commit trips before inserting GPS points.
            # ------------------------------------------------

            self.db_connection.commit()


            # ------------------------------------------------
            # Insert GPS points
            # ------------------------------------------------

            if gps_rows:

                self.cursor.executemany(
                    """
                    INSERT INTO gps_point (
                        trip_id,
                        point_id,
                        latitude,
                        longitude
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    gps_rows
                )


                # ------------------------------------------------
                # Commit GPS points
                # ------------------------------------------------

                self.db_connection.commit()


        except Exception:

            self.db_connection.rollback()

            raise


    # ========================================================
    # Show tables
    # ========================================================

    def show_tables(self):

        self.cursor.execute(
            "SHOW TABLES"
        )

        rows = self.cursor.fetchall()

        print()
        print("Tables in database:")

        for row in rows:

            print(row[0])


    # ========================================================
    # Export database
    # ========================================================

    def export_database(self):

        print()
        print("Exporting database...")

        command = [
            "docker",
            "exec",
            DOCKER_CONTAINER,
            "mysqldump",
            "-u",
            "root",
            "-p6769",
            DATABASE_NAME
        ]

        try:

            with open(
                SQL_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                subprocess.run(
                    command,
                    stdout=file,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )

            print(
                "Database exported to:"
            )

            print(
                SQL_FILE
            )

        except subprocess.CalledProcessError as error:

            print(
                "ERROR: Could not export database."
            )

            print(
                error.stderr
            )

            raise


# ============================================================
# Main
# ============================================================

def main():

    program = None

    try:

        # ----------------------------------------------------
        # Connect to database
        # ----------------------------------------------------

        program = PortoDatabase()


        # ----------------------------------------------------
        # 1. Reset old tables
        # ----------------------------------------------------

        program.reset_tables()


        # ----------------------------------------------------
        # 2. Create tables
        # ----------------------------------------------------

        program.create_tables()


        # ----------------------------------------------------
        # 3. Insert taxis
        # ----------------------------------------------------

        program.insert_taxis()


        # ----------------------------------------------------
        # 4. Insert trips and GPS points
        # ----------------------------------------------------

        program.insert_trips_and_gps()


        # ----------------------------------------------------
        # 5. Show tables
        # ----------------------------------------------------

        program.show_tables()


        # ----------------------------------------------------
        # 6. Export complete database
        # ----------------------------------------------------

        program.export_database()


        print()
        print("-----------------------------------------------")
        print("Database creation finished.")
        print("-----------------------------------------------")


    except Exception as error:

        print()
        print(
            "ERROR: Failed to create database:",
            error
        )


    finally:

        if program:

            program.connection.close_connection()


# ============================================================
# Run program
# ============================================================

if __name__ == "__main__":
    main()