use std::{collections::BTreeMap, error::Error, fs, path::Path};

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct ProtocolCoverage {
    pub version: u32,
    pub entries: Vec<ProtocolCoverageEntry>,
}

#[derive(Debug, Deserialize)]
pub struct ProtocolCoverageEntry {
    pub profile: String,
    pub sidecar: Option<String>,
    pub service: String,
    pub action: String,
    pub op: Option<String>,
    pub suite: String,
    pub environment: String,
    pub transport: String,
    pub destructive: bool,
    pub restore: String,
}

#[derive(Debug, Deserialize)]
pub struct CapabilityMatrix {
    pub version: u32,
    pub bridge: BTreeMap<String, Vec<String>>,
    pub hub: BTreeMap<String, BTreeMap<String, Vec<String>>>,
}

pub fn load_protocol_coverage(
    path: impl AsRef<Path>,
) -> Result<ProtocolCoverage, Box<dyn Error + Send + Sync>> {
    let body = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&body)?)
}

pub fn load_capability_matrix(
    path: impl AsRef<Path>,
) -> Result<CapabilityMatrix, Box<dyn Error + Send + Sync>> {
    let body = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&body)?)
}
