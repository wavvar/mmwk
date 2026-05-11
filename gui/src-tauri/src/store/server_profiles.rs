use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServerProfile {
    pub id: String,
    pub name: String,
    pub mqtt_host: String,
    pub mqtt_port: i64,
    pub http_host: String,
    pub http_port: i64,
    pub shared: bool,
}

pub fn save_server_profile(conn: &Connection, profile: &ServerProfile) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO server_profiles (
            id, name, mqtt_host, mqtt_port, http_host, http_port, shared, updated_at
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, unixepoch())
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            mqtt_host = excluded.mqtt_host,
            mqtt_port = excluded.mqtt_port,
            http_host = excluded.http_host,
            http_port = excluded.http_port,
            shared = excluded.shared,
            updated_at = unixepoch()
        "#,
        params![
            profile.id,
            profile.name,
            profile.mqtt_host,
            profile.mqtt_port,
            profile.http_host,
            profile.http_port,
            profile.shared
        ],
    )?;
    Ok(())
}

pub fn get_server_profile(conn: &Connection, id: &str) -> Result<Option<ServerProfile>> {
    conn.query_row(
        r#"
        SELECT id, name, mqtt_host, mqtt_port, http_host, http_port, shared
        FROM server_profiles
        WHERE id = ?1
        "#,
        [id],
        map_server_profile,
    )
    .optional()
}

pub fn list_server_profiles(conn: &Connection) -> Result<Vec<ServerProfile>> {
    let mut stmt = conn.prepare(
        r#"
        SELECT id, name, mqtt_host, mqtt_port, http_host, http_port, shared
        FROM server_profiles
        ORDER BY name, id
        "#,
    )?;
    let profiles = stmt.query_map([], map_server_profile)?.collect();
    profiles
}

pub fn delete_server_profile(conn: &Connection, id: &str) -> Result<()> {
    conn.execute("DELETE FROM server_profiles WHERE id = ?1", [id])?;
    Ok(())
}

fn map_server_profile(row: &rusqlite::Row<'_>) -> Result<ServerProfile> {
    Ok(ServerProfile {
        id: row.get(0)?,
        name: row.get(1)?,
        mqtt_host: row.get(2)?,
        mqtt_port: row.get(3)?,
        http_host: row.get(4)?,
        http_port: row.get(5)?,
        shared: row.get(6)?,
    })
}
