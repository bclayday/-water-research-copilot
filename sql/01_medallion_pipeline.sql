-- Bronze: raw JSON landing table for USGS payload snapshots
CREATE TABLE IF NOT EXISTS raw_readings (
    raw_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system TEXT NOT NULL DEFAULT 'usgs_nwis',
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

-- Silver: normalized time-series readings by station and parameter
CREATE OR REPLACE VIEW stg_readings AS
SELECT
    wr.reading_id,
    wr.site_id,
    ws.name AS station_name,
    ws.county,
    ws.watershed,
    wr.parameter_code,
    wr.parameter_name,
    wr.value,
    wr.unit,
    wr.reading_time,
    wr.ingested_at,
    CASE
        WHEN wr.parameter_code = '00400' AND (wr.value < 6.5 OR wr.value > 8.5) THEN 'danger'
        WHEN wr.parameter_code = '00400' AND (wr.value < 6.8 OR wr.value > 8.0) THEN 'warning'
        WHEN wr.parameter_code = '63680' AND wr.value > 10 THEN 'danger'
        WHEN wr.parameter_code = '63680' AND wr.value > 5 THEN 'warning'
        WHEN wr.parameter_code = '00300' AND wr.value < 4 THEN 'danger'
        WHEN wr.parameter_code = '00300' AND wr.value < 5 THEN 'warning'
        ELSE 'normal'
    END AS severity
FROM water_readings wr
LEFT JOIN water_stations ws ON ws.site_id = wr.site_id;

-- Gold: station-level health mart using latest values and anomaly weighting
CREATE OR REPLACE VIEW mart_station_health AS
WITH latest AS (
    SELECT DISTINCT ON (site_id, parameter_code)
        site_id,
        parameter_code,
        parameter_name,
        value,
        unit,
        reading_time,
        CASE
            WHEN parameter_code = '00400' AND (value < 6.5 OR value > 8.5) THEN 2
            WHEN parameter_code = '00400' AND (value < 6.8 OR value > 8.0) THEN 1
            WHEN parameter_code = '63680' AND value > 10 THEN 2
            WHEN parameter_code = '63680' AND value > 5 THEN 1
            WHEN parameter_code = '00300' AND value < 4 THEN 2
            WHEN parameter_code = '00300' AND value < 5 THEN 1
            ELSE 0
        END AS risk_points
    FROM water_readings
    ORDER BY site_id, parameter_code, reading_time DESC NULLS LAST
),
scored AS (
    SELECT
        site_id,
        MAX(reading_time) AS latest_reading_time,
        SUM(risk_points) AS total_risk_points,
        MAX(CASE WHEN parameter_code = '00400' THEN value END) AS ph,
        MAX(CASE WHEN parameter_code = '63680' THEN value END) AS turbidity,
        MAX(CASE WHEN parameter_code = '00300' THEN value END) AS dissolved_oxygen,
        MAX(CASE WHEN parameter_code = '00010' THEN value END) AS water_temp_c,
        MAX(CASE WHEN parameter_code = '00060' THEN value END) AS flow_cfs,
        MAX(CASE WHEN parameter_code = '00095' THEN value END) AS conductance_us_cm
    FROM latest
    GROUP BY site_id
)
SELECT
    s.site_id,
    ws.name AS station_name,
    ws.county,
    ws.watershed,
    s.latest_reading_time,
    s.ph,
    s.turbidity,
    s.dissolved_oxygen,
    s.water_temp_c,
    s.flow_cfs,
    s.conductance_us_cm,
    s.total_risk_points,
    CASE
        WHEN s.total_risk_points >= 4 THEN 'danger'
        WHEN s.total_risk_points >= 1 THEN 'warning'
        ELSE 'normal'
    END AS health_status,
    GREATEST(0, 100 - (s.total_risk_points * 20)) AS health_score
FROM scored s
LEFT JOIN water_stations ws ON ws.site_id = s.site_id;
