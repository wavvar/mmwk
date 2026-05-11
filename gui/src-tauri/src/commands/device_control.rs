use std::time::Duration;

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::{
    contracts::model::ProtocolCoverage,
    error::CommandEnvelope,
    protocol::{
        cliv1::Cliv1Request,
        commands::{CommandDescriptor, CommandRegistry},
        envelope::Cliv1Response,
    },
    store::device_profiles::get_device_profile,
    transport::{request_with_retries, CancellationFlag, DeviceTransport, TransportError},
};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DeviceCommandRequest {
    pub device_profile_id: String,
    pub command_id: String,
    #[serde(default)]
    pub args: Value,
    #[serde(default)]
    pub confirmation: Option<String>,
    #[serde(default)]
    pub key: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DeviceCommandResult {
    pub command_id: String,
    pub seq: u64,
    pub raw_response: Cliv1Response,
    pub payload: Value,
}

pub fn registry_from_contracts(
    bridge: &ProtocolCoverage,
    hub: &ProtocolCoverage,
) -> CommandRegistry {
    CommandRegistry::from_coverages([bridge, hub])
}

pub fn execute_device_command_with_transport<T: DeviceTransport>(
    conn: &Connection,
    registry: &CommandRegistry,
    transport: &mut T,
    request: DeviceCommandRequest,
    seq: u64,
) -> CommandEnvelope<DeviceCommandResult> {
    let device = match get_device_profile(conn, &request.device_profile_id) {
        Ok(Some(device)) => device,
        Ok(None) => return CommandEnvelope::error("not_found", "device profile not found"),
        Err(err) => return CommandEnvelope::error("store", err.to_string()),
    };

    let descriptor = match registry.get(&request.command_id) {
        Some(descriptor) => descriptor,
        None => return CommandEnvelope::error("not_found", "command descriptor not found"),
    };

    if descriptor.profile != device.profile {
        return CommandEnvelope::error("unsupported", "command is not available for this profile");
    }
    if descriptor.sidecar.as_deref() != device.sidecar.as_deref()
        && descriptor.sidecar.is_some()
    {
        return CommandEnvelope::error("unsupported", "command sidecar is not available");
    }
    if descriptor.destructive
        && request.confirmation.as_deref() != Some("EXECUTE_DESTRUCTIVE_COMMAND")
    {
        return CommandEnvelope::error(
            "confirmation_required",
            "destructive command requires confirmation",
        );
    }

    let command_id = request.command_id.clone();
    let cliv1 = build_request(seq, descriptor, request.args, request.key);
    match request_with_retries(
        transport,
        &cliv1,
        1,
        Duration::from_secs(10),
        &CancellationFlag::default(),
    ) {
        Ok(response) => {
            if !response.ok {
                return CommandEnvelope::error(
                    response
                        .error
                        .as_ref()
                        .map(|err| err.code.clone())
                        .unwrap_or_else(|| "device_error".to_string()),
                    response
                        .error
                        .as_ref()
                        .map(|err| err.message.clone())
                        .unwrap_or_else(|| "device command failed".to_string()),
                );
            }
            let payload = response.result.clone().unwrap_or_else(|| json!({}));
            CommandEnvelope::success(DeviceCommandResult {
                command_id,
                seq: response.seq,
                raw_response: response,
                payload,
            })
        }
        Err(err) => transport_error(err),
    }
}

fn build_request(
    seq: u64,
    descriptor: &CommandDescriptor,
    args: Value,
    key: Option<String>,
) -> Cliv1Request {
    let request_args = match args {
        Value::Object(mut map) => {
            if let Some(op) = descriptor.op.as_deref() {
                map.entry("op".to_string()).or_insert_with(|| json!(op));
            }
            Value::Object(map)
        }
        Value::Null => {
            let mut map = serde_json::Map::new();
            if let Some(op) = descriptor.op.as_deref() {
                map.insert("op".to_string(), json!(op));
            }
            Value::Object(map)
        }
        other => json!({ "value": other }),
    };

    let mut request = Cliv1Request::new(
        seq,
        descriptor.service.clone(),
        Some(&descriptor.action),
        request_args,
    );
    if let Some(key) = key.filter(|value| !value.is_empty()) {
        request = request.with_key(key);
    }
    request
}

fn transport_error<T>(err: TransportError) -> CommandEnvelope<T> {
    match err {
        TransportError::Timeout => CommandEnvelope::error("timeout", "device command timed out"),
        TransportError::Cancelled => CommandEnvelope::error("cancelled", "device command cancelled"),
        TransportError::Protocol(msg) => CommandEnvelope::error("protocol", msg),
        TransportError::Io(msg) => CommandEnvelope::error("io", msg),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn execute_device_command(
    _state: tauri::State<'_, crate::AppState>,
    request: DeviceCommandRequest,
) -> CommandEnvelope<DeviceCommandResult> {
    let _ = request;
    CommandEnvelope::error(
        "transport_unavailable",
        "device transport runtime is not connected yet",
    )
}
