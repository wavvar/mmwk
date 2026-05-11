use std::time::Duration;

use rusqlite::Connection;
use serde_json::json;

use crate::{
    commands::device_control::{
        execute_device_command_with_transport, registry_from_contracts, DeviceCommandRequest,
    },
    contracts::model::load_protocol_coverage,
    protocol::{
        cliv1::Cliv1Request,
        envelope::{Cliv1Frame, Cliv1Response},
    },
    store::{
        device_profiles::{save_device_profile, DeviceProfile},
        schema::init,
    },
    transport::{DeviceTransport, TransportError},
};

struct MockTransport {
    response: Cliv1Response,
    sent: Vec<Cliv1Request>,
}

impl DeviceTransport for MockTransport {
    fn exchange(
        &mut self,
        request: &Cliv1Request,
        _timeout: Duration,
    ) -> Result<Cliv1Frame, TransportError> {
        self.sent.push(request.clone());
        Ok(Cliv1Frame::Response(self.response.clone()))
    }
}

fn registry() -> crate::protocol::commands::CommandRegistry {
    let bridge =
        load_protocol_coverage("../contracts/protocol_coverage.bridge.json").unwrap();
    let hub = load_protocol_coverage("../contracts/protocol_coverage.hub.json").unwrap();
    registry_from_contracts(&bridge, &hub)
}

fn conn_with_bridge() -> Connection {
    let conn = Connection::open_in_memory().unwrap();
    init(&conn).unwrap();
    save_device_profile(
        &conn,
        &DeviceProfile {
            id: "dev-1".to_string(),
            name: "Bridge".to_string(),
            profile: "bridge".to_string(),
            board: Some("pro".to_string()),
            transport: "mqtt".to_string(),
            serial_port: None,
            baudrate: None,
            mqtt_server_profile_id: None,
            mqtt_prod: "mmwk".to_string(),
            mqtt_oid: "mmwk".to_string(),
            mqtt_cid: None,
            mqtt_did: Some("dc5475c8784c".to_string()),
            sidecar: None,
        },
    )
    .unwrap();
    conn
}

#[test]
fn executes_node_info_and_exposes_raw_payload() {
    let conn = conn_with_bridge();
    let registry = registry();
    let mut transport = MockTransport {
        response: Cliv1Response {
            seq: 42,
            ok: true,
            result: Some(json!({"did": "dc5475c8784c", "raw_data": "mmwk/mmwk/d/raw/data"})),
            error: None,
        },
        sent: Vec::new(),
    };

    let result = execute_device_command_with_transport(
        &conn,
        &registry,
        &mut transport,
        DeviceCommandRequest {
            device_profile_id: "dev-1".to_string(),
            command_id: "bridge/node/info".to_string(),
            args: json!({}),
            confirmation: None,
            key: None,
        },
        42,
    );

    assert!(result.ok, "{:?}", result.error);
    let data = result.data.unwrap();
    assert_eq!(data.payload["did"], "dc5475c8784c");
    assert_eq!(data.raw_response.result.unwrap()["raw_data"], "mmwk/mmwk/d/raw/data");
    assert_eq!(transport.sent[0].service, "node");
    assert_eq!(transport.sent[0].action.as_deref(), Some("info"));
}

#[test]
fn executes_network_and_radar_status() {
    let conn = conn_with_bridge();
    let registry = registry();

    for command_id in ["bridge/network/status", "bridge/radar/status"] {
        let mut transport = MockTransport {
            response: Cliv1Response {
                seq: 7,
                ok: true,
                result: Some(json!({"status": "ok"})),
                error: None,
            },
            sent: Vec::new(),
        };

        let result = execute_device_command_with_transport(
            &conn,
            &registry,
            &mut transport,
            DeviceCommandRequest {
                device_profile_id: "dev-1".to_string(),
                command_id: command_id.to_string(),
                args: json!({}),
                confirmation: None,
                key: None,
            },
            7,
        );

        assert!(result.ok, "{command_id} failed: {:?}", result.error);
    }
}

#[test]
fn destructive_commands_require_confirmation_token() {
    let conn = conn_with_bridge();
    let registry = registry();
    let mut transport = MockTransport {
        response: Cliv1Response {
            seq: 1,
            ok: true,
            result: Some(json!({})),
            error: None,
        },
        sent: Vec::new(),
    };

    let result = execute_device_command_with_transport(
        &conn,
        &registry,
        &mut transport,
        DeviceCommandRequest {
            device_profile_id: "dev-1".to_string(),
            command_id: "bridge/node/reboot".to_string(),
            args: json!({}),
            confirmation: None,
            key: None,
        },
        1,
    );

    assert!(!result.ok);
    assert_eq!(result.error.unwrap().code, "confirmation_required");
    assert!(transport.sent.is_empty());
}
