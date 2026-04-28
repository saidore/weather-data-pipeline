-- schema.sql
-- Author: Xitai (revised by Zijiang)

-- Two tables: locations + weather_observations
-- TIMESTAMP supports daily/hourly resolution
-- Store both units so we don't need to convert in queries


-- 1. location table: one row per city
CREATE TABLE locations (
    id          SERIAL PRIMARY KEY,
    city        VARCHAR(100) NOT NULL UNIQUE,
    latitude    FLOAT NOT NULL,
    longitude   FLOAT NOT NULL,
    elevation   FLOAT,
    timezone    VARCHAR(50)
);


-- 2. observation table: one row per city per time point
CREATE TABLE weather_observations (
    id              SERIAL PRIMARY KEY,
    location_id     INTEGER NOT NULL REFERENCES locations(id),
    time            TIMESTAMP NOT NULL,

    -- temperature in both units
    temp_c          FLOAT,
    temp_f          FLOAT,

    -- precipitation in both units
    precip_mm       FLOAT,
    precip_inch     FLOAT,

    -- wind speed in both units
    wind_speed_kmh  FLOAT,
    wind_speed_mph  FLOAT,

    -- no duplicate rows if we rerun the pipeline
    UNIQUE (location_id, time)
);