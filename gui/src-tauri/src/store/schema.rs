use rusqlite::{Connection, Result};

pub fn init(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS device_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            profile TEXT NOT NULL,
            board TEXT,
            transport TEXT NOT NULL,
            serial_port TEXT,
            baudrate INTEGER,
            mqtt_server_profile_id TEXT,
            mqtt_prod TEXT NOT NULL,
            mqtt_oid TEXT NOT NULL,
            mqtt_cid TEXT,
            mqtt_did TEXT,
            sidecar TEXT,
            updated_at INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS server_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mqtt_host TEXT NOT NULL,
            mqtt_port INTEGER NOT NULL,
            http_host TEXT NOT NULL,
            http_port INTEGER NOT NULL,
            shared INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS artifact_runs (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            completed_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS run_artifacts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            bytes INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(run_id) REFERENCES artifact_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS command_audit (
            id TEXT PRIMARY KEY,
            device_profile_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS hub_event_runs (
            id TEXT PRIMARY KEY,
            device_profile_id TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            completed_at INTEGER,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hub_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            device_profile_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload BLOB NOT NULL,
            decoded_json TEXT,
            decode_status TEXT NOT NULL,
            received_at INTEGER NOT NULL,
            FOREIGN KEY(run_id) REFERENCES hub_event_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS video_configs (
            id TEXT PRIMARY KEY,
            device_profile_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_uri TEXT NOT NULL,
            required_for_run INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (unixepoch())
        );
        "#,
    )
}
