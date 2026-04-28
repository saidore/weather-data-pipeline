# Requirement Specification

This system is Apache Airflow pipeline project which is designed to provide a reliable data foundation for climate data analysis. Data obtained from API is unstable. To support data analysis, this climate data pipeline is built to ingest data from API, transform this data into an analysis-ready form and store this data in PostgreSQL database.

## Input Requirement

The data obtained from API is in JSON format. It contains many attributes, including latitude, longitude, elevation, generationtime_ms, utc_offset_seconds, timezone, timezone_abbreviation, hourly, hourly_units, daily, daily_units. Additionally, the value of hourly/daily is a dict which contains the queried lists of observation times and values.

### Other Details

- For more information, see the official website of API: [Historical Weather API | Open-Meteo.com](https://open-meteo.com/en/docs/historical-weather-api)
- Data is fetched for configurable cities and time ranges via config.yaml.
- Uses daily resolution: temperature_2m_mean, precipitation_sum, wind_speed_10m_max.
- Raw JSON is stored in MongoDB with metadata (city, coordinates, timestamps).
- MinIO provides backup copy of raw JSON files.

## Output Requirements

Two tables are stored in PostgreSQL:

The first table is locations table which represents information on all locations queried. It has six attributes: id, city, latitude, longitude, elevation, timezone. The other one is weather_observations which contain the queried time and all climate data of the location at the time, including temp_c, temp_f, precip_mm, precip_inch, wind_speed_kmh, wind_speed_mph. weather_observation is bound to locations by location_id. Data with respect to different units are stored to avoid unit conversion. As a result, the database allows query by time, aggregation by location, comparison between regions. Downstream can perform climate trend analysis, extreme weather detection, variability metrics, geospatial analysis, etc.

### Other Details

- weather_observations includes 'time' field (TIMESTAMP) for temporal queries.
- UNIQUE constraint on (location_id, time) prevents duplicate records.
- Supports hourly/daily resolution (schema supports both).

## Limitation

1. Schema only supports three types of metrics: temperature, wind_speed, and precipitation. If a new metric is introduced, schema should be rewritten.
2. If new metric is introduced, ETL should be updated.
3. Dependent on external API (Open-Meteo) availability and rate limits.
4. Pipeline runs manually, no automated scheduling currently.
5. No incremental updates - full historical fetch each run.

## Requirements

- On node0: MicroK8s, Helm, Airflow, MongoDB, PostgreSQL, MinIO and Custom Airflow image.
- Python library: requests, pyyaml, pymongo, minio, psycopg2-binary, pandas, pendulum.
- docker-compose.yaml for local development.
- config.yaml for pipeline parameters.
- Schema.sql for database initialization.
