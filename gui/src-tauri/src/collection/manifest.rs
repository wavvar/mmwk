use std::path::PathBuf;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunArtifact {
    pub device_id: String,
    pub kind: String,
    pub path: PathBuf,
    pub bytes: u64,
    pub messages: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunManifest {
    pub run_id: String,
    pub interrupted: bool,
    pub artifacts: Vec<RunArtifact>,
}
