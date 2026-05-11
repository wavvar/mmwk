use rusqlite::Connection;

use crate::{
    commands::profiles::{
        delete_device_profile_command, delete_server_profile_command, list_device_profiles_command,
        list_server_profiles_command, save_device_profile_command, save_server_profile_command,
    },
    store::{
        device_profiles::DeviceProfile,
        schema::init,
        server_profiles::ServerProfile,
    },
};

#[test]
fn profile_commands_return_success_envelopes() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let server = ServerProfile {
        id: "srv-1".to_string(),
        name: "Bench services".to_string(),
        mqtt_host: "127.0.0.1".to_string(),
        mqtt_port: 1883,
        http_host: "127.0.0.1".to_string(),
        http_port: 8080,
        shared: true,
    };
    let device = DeviceProfile {
        id: "dev-1".to_string(),
        name: "Hub WDR".to_string(),
        profile: "hub".to_string(),
        board: Some("wdr".to_string()),
        transport: "mqtt".to_string(),
        serial_port: None,
        baudrate: None,
        mqtt_server_profile_id: Some("srv-1".to_string()),
        mqtt_prod: "mmwk".to_string(),
        mqtt_oid: "mmwk".to_string(),
        mqtt_cid: None,
        mqtt_did: Some("1020ba76b404".to_string()),
        sidecar: Some("care".to_string()),
    };

    let saved_server = save_server_profile_command(&conn, server.clone());
    assert!(saved_server.ok);
    assert_eq!(saved_server.data, Some(server));

    let saved_device = save_device_profile_command(&conn, device.clone());
    assert!(saved_device.ok);
    assert_eq!(saved_device.data, Some(device.clone()));

    let servers = list_server_profiles_command(&conn);
    assert_eq!(servers.data.unwrap().len(), 1);

    let devices = list_device_profiles_command(&conn);
    assert_eq!(devices.data, Some(vec![device]));
}

#[test]
fn profile_commands_return_normalized_validation_errors() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let result = save_server_profile_command(
        &conn,
        ServerProfile {
            id: "".to_string(),
            name: "Missing id".to_string(),
            mqtt_host: "127.0.0.1".to_string(),
            mqtt_port: 1883,
            http_host: "127.0.0.1".to_string(),
            http_port: 8080,
            shared: true,
        },
    );

    assert!(!result.ok);
    assert_eq!(result.error.unwrap().code, "validation");
}

#[test]
fn profile_commands_delete_profiles() {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();

    let server = ServerProfile {
        id: "srv-1".to_string(),
        name: "Bench services".to_string(),
        mqtt_host: "127.0.0.1".to_string(),
        mqtt_port: 1883,
        http_host: "127.0.0.1".to_string(),
        http_port: 8080,
        shared: true,
    };
    save_server_profile_command(&conn, server);
    assert!(delete_server_profile_command(&conn, "srv-1".to_string()).ok);
    assert_eq!(list_server_profiles_command(&conn).data.unwrap().len(), 0);

    assert!(delete_device_profile_command(&conn, "dev-1".to_string()).ok);
}
