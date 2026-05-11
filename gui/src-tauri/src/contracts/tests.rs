use std::path::PathBuf;

use super::model::{load_capability_matrix, load_protocol_coverage};

fn contract_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../contracts")
        .join(name)
}

#[test]
fn loads_bridge_and_hub_coverage() {
    let bridge = load_protocol_coverage(contract_path("protocol_coverage.bridge.json")).unwrap();
    let hub = load_protocol_coverage(contract_path("protocol_coverage.hub.json")).unwrap();

    assert!(bridge
        .entries
        .iter()
        .any(|entry| entry.profile == "bridge" && entry.service == "node"));
    assert!(hub
        .entries
        .iter()
        .any(|entry| entry.profile == "hub" && entry.service == "scene"));
}

#[test]
fn loads_capability_matrix() {
    let matrix = load_capability_matrix(contract_path("capability_matrix.json")).unwrap();

    assert!(matrix.bridge["mini"].contains(&"core".to_string()));
    assert!(matrix.hub["pro"]["care"].contains(&"hub".to_string()));
}
