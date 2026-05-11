use serde::Serialize;
use serde_json::Value;
use thiserror::Error;

use super::envelope::{Cliv1Error, Cliv1Event, Cliv1Frame, Cliv1Response};

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Cliv1Request {
    #[serde(rename = "type")]
    message_type: &'static str,
    pub seq: u64,
    pub service: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub action: Option<String>,
    pub args: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub key: Option<String>,
}

impl Cliv1Request {
    pub fn new(seq: u64, service: impl Into<String>, action: Option<&str>, args: Value) -> Self {
        Self {
            message_type: "req",
            seq,
            service: service.into(),
            action: action.map(ToOwned::to_owned),
            args,
            key: None,
        }
    }

    pub fn with_key(mut self, key: impl Into<String>) -> Self {
        self.key = Some(key.into());
        self
    }
}

#[derive(Debug, Error)]
pub enum Cliv1ErrorKind {
    #[error("invalid cliv1 json: {0}")]
    InvalidJson(#[from] serde_json::Error),
    #[error("unsupported cliv1 frame")]
    UnsupportedFrame,
}

pub fn serialize_request_line(request: &Cliv1Request) -> Result<String, serde_json::Error> {
    let mut line = serde_json::to_string(request)?;
    line.push('\n');
    Ok(line)
}

pub fn parse_frame(line: &str) -> Result<Cliv1Frame, Cliv1ErrorKind> {
    let trimmed = line.trim();
    if !trimmed.contains('{') {
        return Ok(Cliv1Frame::Text(trimmed.to_string()));
    }

    let json_text = extract_json_object(trimmed).unwrap_or(trimmed);
    let value: Value = serde_json::from_str(json_text)?;
    let message_type = value
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default();

    match message_type {
        "res" => parse_response(value),
        "evt" => parse_event(value),
        _ => Ok(Cliv1Frame::Text(trimmed.to_string())),
    }
}

fn parse_response(value: Value) -> Result<Cliv1Frame, Cliv1ErrorKind> {
    let response = Cliv1Response {
        seq: value
            .get("seq")
            .and_then(Value::as_u64)
            .ok_or(Cliv1ErrorKind::UnsupportedFrame)?,
        ok: value.get("ok").and_then(Value::as_bool).unwrap_or(false),
        result: value.get("result").cloned(),
        error: value.get("error").map(parse_error).transpose()?,
    };
    Ok(Cliv1Frame::Response(response))
}

fn parse_error(value: &Value) -> Result<Cliv1Error, Cliv1ErrorKind> {
    if !value.is_object() {
        return Err(Cliv1ErrorKind::UnsupportedFrame);
    }
    Ok(Cliv1Error {
        code: value
            .get("code")
            .and_then(Value::as_str)
            .unwrap_or("error")
            .to_string(),
        message: value
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("CLI request failed")
            .to_string(),
        data: value.get("data").cloned(),
    })
}

fn parse_event(value: Value) -> Result<Cliv1Frame, Cliv1ErrorKind> {
    let event = Cliv1Event {
        service: required_string(&value, "service")?,
        event: required_string(&value, "event")?,
        ts: value
            .get("ts")
            .and_then(Value::as_i64)
            .ok_or(Cliv1ErrorKind::UnsupportedFrame)?,
        data: value.get("data").cloned().unwrap_or(Value::Null),
    };
    Ok(Cliv1Frame::Event(event))
}

fn required_string(value: &Value, key: &'static str) -> Result<String, Cliv1ErrorKind> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .ok_or(Cliv1ErrorKind::UnsupportedFrame)
}

fn extract_json_object(text: &str) -> Option<&str> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if start <= end {
        Some(&text[start..=end])
    } else {
        None
    }
}
