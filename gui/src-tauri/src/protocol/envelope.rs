use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Cliv1Error {
    pub code: String,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Cliv1Response {
    pub seq: u64,
    pub ok: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<Cliv1Error>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Cliv1Event {
    pub service: String,
    pub event: String,
    pub ts: i64,
    #[serde(default)]
    pub data: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Cliv1Frame {
    Response(Cliv1Response),
    Event(Cliv1Event),
    Text(String),
}
