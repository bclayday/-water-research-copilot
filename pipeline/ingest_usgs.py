from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import psycopg2
import requests
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, explode

USGS_URL = (
    "https://waterservices.usgs.gov/nwis/iv/?format=json"
    "&sites=02334430,02334480,02388985,02389150,02394682"
    "&parameterCd=00010,00400,63680,00300,00060,00095&siteStatus=all"
)

STATIONS = {
    "02394682": {"name": "Richland Creek at Old Dallas Rd", "latitude": 33.9286, "longitude": -84.8409, "watershed": "Etowah", "county": "Paulding"},
    "02334430": {"name": "Chattahoochee River at Buford Dam", "latitude": 34.1576, "longitude": -84.0713, "watershed": "Chattahoochee", "county": "Gwinnett"},
    "02388985": {"name": "Russell Creek near Dawsonville", "latitude": 34.3937, "longitude": -84.1191, "watershed": "Etowah", "county": "Dawson"},
    "02389150": {"name": "Etowah River at GA 9", "latitude": 34.4215, "longitude": -84.1184, "watershed": "Etowah", "county": "Dawson"},
    "02334480": {"name": "Richland Creek at Suwanee Dam Rd", "latitude": 34.1228, "longitude": -84.0062, "watershed": "Chattahoochee", "county": "Gwinnett"},
}

PARAMETER_META = {
    "00010": {"name": "Water Temperature", "unit": "deg C"},
    "00400": {"name": "pH", "unit": "pH"},
    "63680": {"name": "Turbidity", "unit": "FNU"},
    "00300": {"name": "Dissolved Oxygen", "unit": "mg/L"},
    "00060": {"name": "Flow", "unit": "cfs"},
    "00095": {"name": "Specific Conductance", "unit": "uS/cm"},
}


def get_connection() -> psycopg2.extensions.connection:
    import os

    return psycopg2.connect(os.environ["LAKEBASE_URL"], sslmode="require")


def detect_anomaly(parameter_code: str, value: float | None) -> tuple[str, float] | None:
    if value is None:
        return None
    if parameter_code == "00400":
        if value < 6.5:
            return "danger", 6.5
        if value > 8.5:
            return "danger", 8.5
        if value < 6.8:
            return "warning", 6.8
        if value > 8.0:
            return "warning", 8.0
    elif parameter_code == "63680":
        if value > 10:
            return "danger", 10.0
        if value > 5:
            return "warning", 5.0
    elif parameter_code == "00300":
        if value < 4:
            return "danger", 4.0
        if value < 5:
            return "warning", 5.0
    return None


def upsert_stations(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        for site_id, meta in STATIONS.items():
            cur.execute(
                """
                INSERT INTO water_stations (site_id, name, latitude, longitude, watershed, county)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (site_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    watershed = EXCLUDED.watershed,
                    county = EXCLUDED.county
                """,
                (site_id, meta["name"], meta["latitude"], meta["longitude"], meta["watershed"], meta["county"]),
            )
    conn.commit()


def write_results(conn: psycopg2.extensions.connection, rows: list[dict[str, Any]]) -> tuple[int, int]:
    readings_written = 0
    anomalies_written = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO water_readings (site_id, parameter_code, parameter_name, value, unit, reading_time)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["site_id"],
                    row["parameter_code"],
                    row["parameter_name"],
                    row["value"],
                    row["unit"],
                    row["reading_time"],
                ),
            )
            readings_written += 1

            anomaly = detect_anomaly(row["parameter_code"], row["value"])
            if anomaly:
                severity, threshold = anomaly
                cur.execute(
                    """
                    INSERT INTO water_anomalies (site_id, parameter_name, value, threshold, severity, detected_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["site_id"],
                        row["parameter_name"],
                        row["value"],
                        threshold,
                        severity,
                        row["reading_time"],
                    ),
                )
                anomalies_written += 1
    conn.commit()
    return readings_written, anomalies_written


def main() -> None:
    spark = SparkSession.builder.appName("USGSWaterIngest").getOrCreate()
    response = requests.get(USGS_URL, timeout=30)
    response.raise_for_status()

    raw_df = spark.read.json(spark.sparkContext.parallelize([response.text]))
    exploded_df = (
        raw_df.select(explode(col("value.timeSeries")).alias("series"))
        .select(
            col("series.sourceInfo.siteCode")[0]["value"].alias("site_id"),
            col("series.variable.variableCode")[0]["value"].alias("parameter_code"),
            col("series.variable.variableName").alias("variable_name"),
            explode(col("series.values")).alias("value_set"),
        )
        .select(
            col("site_id"),
            col("parameter_code"),
            col("variable_name"),
            explode(col("value_set.value")).alias("reading"),
        )
        .select(
            col("site_id"),
            col("parameter_code"),
            col("variable_name"),
            col("reading.value").cast("double").alias("value"),
            col("reading.dateTime").alias("reading_time"),
        )
    )

    rows: list[dict[str, Any]] = []
    for row in exploded_df.collect():
        meta = PARAMETER_META.get(row["parameter_code"], {"name": row["variable_name"], "unit": None})
        rows.append(
            {
                "site_id": row["site_id"],
                "parameter_code": row["parameter_code"],
                "parameter_name": meta["name"],
                "value": row["value"],
                "unit": meta["unit"],
                "reading_time": datetime.fromisoformat(row["reading_time"].replace("Z", "+00:00")) if row["reading_time"] else None,
            }
        )

    conn = get_connection()
    upsert_stations(conn)
    readings_written, anomalies_written = write_results(conn, rows)
    conn.close()
    spark.stop()
    print(json.dumps({"readings_written": readings_written, "anomalies_written": anomalies_written}, default=str))


if __name__ == "__main__":
    main()
