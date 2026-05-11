use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeviceProfile {
    pub id: String,
    pub name: String,
    pub profile: String,
    pub board: Option<String>,
    pub transport: String,
    pub serial_port: Option<String>,
    pub baudrate: Option<i64>,
    pub mqtt_server_profile_id: Option<String>,
    pub mqtt_prod: String,
    pub mqtt_oid: String,
    pub mqtt_cid: Option<String>,
    pub mqtt_did: Option<String>,
    pub sidecar: Option<String>,
}

pub fn save_device_profile(conn: &Connection, profile: &DeviceProfile) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO device_profiles (
            id, name, profile, board, transport, serial_port, baudrate,
            mqtt_server_profile_id, mqtt_prod, mqtt_oid, mqtt_cid, mqtt_did, sidecar, updated_at
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, unixepoch())
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            profile = excluded.profile,
            board = excluded.board,
            transport = excluded.transport,
            serial_port = excluded.serial_port,
            baudrate = excluded.baudrate,
            mqtt_server_profile_id = excluded.mqtt_server_profile_id,
            mqtt_prod = excluded.mqtt_prod,
            mqtt_oid = excluded.mqtt_oid,
            mqtt_cid = excluded.mqtt_cid,
            mqtt_did = excluded.mqtt_did,
            sidecar = excluded.sidecar,
            updated_at = unixepoch()
        "#,
        params![
            profile.id,
            profile.name,
            profile.profile,
            profile.board,
            profile.transport,
            profile.serial_port,
            profile.baudrate,
            profile.mqtt_server_profile_id,
            profile.mqtt_prod,
            profile.mqtt_oid,
            profile.mqtt_cid,
            profile.mqtt_did,
            profile.sidecar
        ],
    )?;
    Ok(())
}

pub fn get_device_profile(conn: &Connection, id: &str) -> Result<Option<DeviceProfile>> {
    conn.query_row(
        r#"
        SELECT id, name, profile, board, transport, serial_port, baudrate,
               mqtt_server_profile_id, mqtt_prod, mqtt_oid, mqtt_cid, mqtt_did, sidecar
        FROM device_profiles
        WHERE id = ?1
        "#,
        [id],
        map_device_profile,
    )
    .optional()
}

pub fn list_device_profiles(conn: &Connection) -> Result<Vec<DeviceProfile>> {
    let mut stmt = conn.prepare(
        r#"
        SELECT id, name, profile, board, transport, serial_port, baudrate,
               mqtt_server_profile_id, mqtt_prod, mqtt_oid, mqtt_cid, mqtt_did, sidecar
        FROM device_profiles
        ORDER BY name, id
        "#,
    )?;
    let profiles = stmt.query_map([], map_device_profile)?.collect();
    profiles
}

fn map_device_profile(row: &rusqlite::Row<'_>) -> Result<DeviceProfile> {
    Ok(DeviceProfile {
        id: row.get(0)?,
        name: row.get(1)?,
        profile: row.get(2)?,
        board: row.get(3)?,
        transport: row.get(4)?,
        serial_port: row.get(5)?,
        baudrate: row.get(6)?,
        mqtt_server_profile_id: row.get(7)?,
        mqtt_prod: row.get(8)?,
        mqtt_oid: row.get(9)?,
        mqtt_cid: row.get(10)?,
        mqtt_did: row.get(11)?,
        sidecar: row.get(12)?,
    })
}
