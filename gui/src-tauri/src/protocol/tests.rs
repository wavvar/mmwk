use std::path::PathBuf;

use crate::{
    contracts::model::load_protocol_coverage,
    protocol::{
        commands::CommandRegistry,
        topics::{derive_mqtt_topics, MqttRoute},
    },
};

fn contract_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../contracts")
        .join(name)
}

#[test]
fn command_registry_covers_bridge_and_hub_contract_entries() {
    let bridge = load_protocol_coverage(contract_path("protocol_coverage.bridge.json")).unwrap();
    let hub = load_protocol_coverage(contract_path("protocol_coverage.hub.json")).unwrap();
    let registry = CommandRegistry::from_coverages([&bridge, &hub]);

    for entry in bridge.entries.iter().chain(hub.entries.iter()) {
        assert!(
            registry.find_entry(entry).is_some(),
            "missing descriptor for {}/{}/{}/{} sidecar={:?}",
            entry.profile,
            entry.service,
            entry.action,
            entry.op.as_deref().unwrap_or(""),
            entry.sidecar
        );
    }
}

#[test]
fn command_registry_groups_bridge_and_hub_sidecar_controls() {
    let bridge = load_protocol_coverage(contract_path("protocol_coverage.bridge.json")).unwrap();
    let hub = load_protocol_coverage(contract_path("protocol_coverage.hub.json")).unwrap();
    let registry = CommandRegistry::from_coverages([&bridge, &hub]);

    assert_eq!(
        registry
            .find("bridge", None, "node", "info", None)
            .unwrap()
            .ui_group,
        "device"
    );
    assert_eq!(
        registry
            .find("hub", None, "scene", "read", None)
            .unwrap()
            .ui_group,
        "hub"
    );
    assert_eq!(
        registry
            .find(
                "hub",
                Some("care"),
                "care.rfcare",
                "transfer_0x21_raw_data_rx",
                None,
            )
            .unwrap()
            .ui_group,
        "care"
    );
    assert_eq!(
        registry
            .find("hub", Some("rmaker"), "rmaker", "sidecar_contract", None)
            .unwrap()
            .ui_group,
        "rmaker"
    );
}

#[test]
fn mqtt_topics_fall_back_to_did_for_unclaimed_devices() {
    let topics = derive_mqtt_topics(MqttRoute {
        prod: "mmwk",
        oid: "mmwk",
        did: "dc5475c879c0",
        cid: "",
        include_raw_cmd: true,
    })
    .unwrap();

    assert_eq!(topics.cmd, "mmwk/mmwk/dc5475c879c0/device/cmd");
    assert_eq!(topics.resp, "mmwk/mmwk/dc5475c879c0/device/resp");
    assert_eq!(topics.raw_data, "mmwk/mmwk/dc5475c879c0/raw/data");
    assert_eq!(topics.raw_resp, "mmwk/mmwk/dc5475c879c0/raw/resp");
    assert_eq!(topics.raw_cmd, "mmwk/mmwk/dc5475c879c0/raw/cmd");
    assert_eq!(topics.hub_inquiry, "mmwk/mmwk/dc5475c879c0/hub/inquiry");
    assert_eq!(topics.hub_config, "mmwk/mmwk/dc5475c879c0/hub/config");
    assert_eq!(topics.stream_in, "mmwk/mmwk/dc5475c879c0/stream/in");
    assert_eq!(topics.stream_ack, topics.resp);
}

#[test]
fn mqtt_topics_prefer_cid_and_preserve_claimed_route_case() {
    let topics = derive_mqtt_topics(MqttRoute {
        prod: "Acme",
        oid: "Org001",
        did: "dc5475c879c0",
        cid: "VeABC123",
        include_raw_cmd: true,
    })
    .unwrap();

    assert_eq!(topics.cmd, "Acme/Org001/VeABC123/device/cmd");
    assert_eq!(topics.raw_data, "Acme/Org001/VeABC123/raw/data");
    assert_eq!(topics.stream_in, "Acme/Org001/VeABC123/stream/in");
}

#[test]
fn mqtt_topics_gate_raw_cmd() {
    let topics = derive_mqtt_topics(MqttRoute {
        prod: "acme",
        oid: "org001",
        did: "dc5475c879c0",
        cid: "",
        include_raw_cmd: false,
    })
    .unwrap();

    assert_eq!(topics.raw_cmd, "");
}

#[test]
fn mqtt_topics_reject_missing_or_invalid_route_segments() {
    let missing = derive_mqtt_topics(MqttRoute {
        prod: "acme",
        oid: "org001",
        did: "",
        cid: "",
        include_raw_cmd: true,
    });
    assert!(missing.is_err());

    let invalid = derive_mqtt_topics(MqttRoute {
        prod: "acme/root",
        oid: "org001",
        did: "device",
        cid: "",
        include_raw_cmd: true,
    });
    assert!(invalid.is_err());
}
