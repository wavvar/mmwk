use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SerialTransportConfig {
    pub port: String,
    pub baudrate: u32,
    pub reset_on_connect: bool,
}
