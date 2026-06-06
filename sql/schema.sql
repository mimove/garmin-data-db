CREATE TABLE IF NOT EXISTS daily_summary (
    calendar_date DATE PRIMARY KEY,
    steps INTEGER,
    calories_total INTEGER,
    calories_active INTEGER,
    floors REAL,
    intensity_minutes_moderate INTEGER,
    intensity_minutes_vigorous INTEGER,
    resting_hr INTEGER,
    min_hr INTEGER,
    max_hr INTEGER,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS sleep (
    calendar_date DATE PRIMARY KEY,
    score INTEGER,
    duration_sec INTEGER,
    deep_sec INTEGER,
    light_sec INTEGER,
    rem_sec INTEGER,
    awake_sec INTEGER,
    avg_spo2 REAL,
    avg_respiration REAL,
    sleep_start TIMESTAMPTZ,
    sleep_end TIMESTAMPTZ,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS hrv (
    calendar_date DATE PRIMARY KEY,
    last_night_avg_ms REAL,
    weekly_avg_ms REAL,
    status TEXT,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS training_status (
    calendar_date DATE PRIMARY KEY,
    vo2max REAL,
    training_load_7d REAL,
    status TEXT,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS hr_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    bpm INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS stress_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stress_level INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS body_battery_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    level INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS respiration_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    breaths_per_min REAL,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS spo2_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    spo2_pct REAL,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS steps_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    steps INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id BIGINT PRIMARY KEY,
    type TEXT,
    name TEXT,
    start_time TIMESTAMPTZ,
    distance_m REAL,
    duration_sec REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_pace_s_per_km REAL,
    calories REAL,
    vo2max REAL,
    aerobic_training_effect REAL,
    anaerobic_training_effect REAL,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS activity_splits (
    activity_id BIGINT NOT NULL,
    split_index INTEGER NOT NULL,
    distance_m REAL,
    duration_sec REAL,
    avg_hr REAL,
    avg_pace_s_per_km REAL,
    elevation_gain_m REAL,
    PRIMARY KEY (activity_id, split_index)
);

CREATE TABLE IF NOT EXISTS sync_log (
    calendar_date DATE PRIMARY KEY,
    synced_at TIMESTAMPTZ DEFAULT now()
);
