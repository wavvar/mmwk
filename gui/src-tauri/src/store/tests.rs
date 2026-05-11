use rusqlite::Connection;

use super::{
    device_profiles::{get_device_profile, list_device_profiles, save_device_profile, DeviceProfile},
    runs::{create_run, get_run, ArtifactRun},
    schema::init,
    server_profiles::{get_server_profile, save_server_profile, ServerProfile},
};

#[test]
fn stores_and_updates_device_profiles() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let mut profile = DeviceProfile {
        id: "dev-1".to_string(),
        name: "Lab PRO".to_string(),
        profile: "bridge".to_string(),
        board: Some("pro".to_string()),
        transport: "mqtt".to_string(),
        serial_port: None,
        baudrate: None,
        mqtt_server_profile_id: Some("srv-1".to_string()),
        mqtt_prod: "mmwk".to_string(),
        mqtt_oid: "mmwk".to_string(),
        mqtt_cid: None,
        mqtt_did: Some("dc5475c8784c".to_string()),
        sidecar: None,
    };

    save_device_profile(&conn, &profile).unwrap();
    assert_eq!(get_device_profile(&conn, "dev-1").unwrap().unwrap(), profile);

    profile.name = "Lab PRO Updated".to_string();
    profile.sidecar = Some("care".to_string());
    save_device_profile(&conn, &profile).unwrap();

    assert_eq!(list_device_profiles(&conn).unwrap(), vec![profile]);
}

#[test]
fn stores_reusable_server_profiles() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let server = ServerProfile {
        id: "srv-1".to_string(),
        name: "Local bench".to_string(),
        mqtt_host: "127.0.0.1".to_string(),
        mqtt_port: 1883,
        http_host: "127.0.0.1".to_string(),
        http_port: 8080,
        shared: true,
    };

    save_server_profile(&conn, &server).unwrap();

    assert_eq!(get_server_profile(&conn, "srv-1").unwrap().unwrap(), server);
}

#[test]
fn stores_run_manifest_stubs() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let run = ArtifactRun {
        id: "run-1".to_string(),
        label: "morning capture".to_string(),
        status: "running".to_string(),
        started_at: 1_800_000_000,
        completed_at: None,
    };

    create_run(&conn, &run).unwrap();

    assert_eq!(get_run(&conn, "run-1").unwrap().unwrap(), run);
}
