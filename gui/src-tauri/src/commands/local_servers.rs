use serde::{Deserialize, Serialize};

use crate::{
    error::CommandEnvelope,
    services::http_server::{status_from_config, HttpServerConfig, HttpServerStatus},
    services::mqtt_broker::{MqttBrokerConfig, MqttBrokerRuntime, MqttBrokerStatus},
};

#[derive(Debug, Default)]
pub struct HttpServerRuntime {
    config: Option<HttpServerConfig>,
    running: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocalServerStatus {
    pub http: Option<HttpServerStatus>,
    pub mqtt: Option<MqttBrokerStatus>,
}

pub fn start_http_server_command(
    runtime: &mut HttpServerRuntime,
    config: HttpServerConfig,
) -> CommandEnvelope<HttpServerStatus> {
    if config.host.trim().is_empty() {
        return CommandEnvelope::error("validation", "HTTP host is required");
    }

    runtime.running = true;
    runtime.config = Some(config.clone());
    CommandEnvelope::success(status_from_config(&config, true))
}

pub fn stop_http_server_command(runtime: &mut HttpServerRuntime) -> CommandEnvelope<()> {
    runtime.running = false;
    CommandEnvelope::success(())
}

pub fn get_http_server_status_command(
    runtime: &HttpServerRuntime,
) -> CommandEnvelope<LocalServerStatus> {
    let http = runtime
        .config
        .as_ref()
        .map(|config| status_from_config(config, runtime.running));
    CommandEnvelope::success(LocalServerStatus { http, mqtt: None })
}

pub fn start_mqtt_broker_command(
    runtime: &mut MqttBrokerRuntime,
    config: MqttBrokerConfig,
) -> CommandEnvelope<MqttBrokerStatus> {
    if config.host.trim().is_empty() {
        return CommandEnvelope::error("validation", "MQTT host is required");
    }
    CommandEnvelope::success(runtime.start(config))
}

pub fn stop_mqtt_broker_command(runtime: &mut MqttBrokerRuntime) -> CommandEnvelope<()> {
    runtime.stop();
    CommandEnvelope::success(())
}

pub fn get_mqtt_broker_status_command(
    runtime: &MqttBrokerRuntime,
) -> CommandEnvelope<MqttBrokerStatus> {
    CommandEnvelope::success(runtime.status())
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn start_http_server(
    state: tauri::State<'_, crate::AppState>,
    config: HttpServerConfig,
) -> CommandEnvelope<HttpServerStatus> {
    match state.http_server.lock() {
        Ok(mut runtime) => start_http_server_command(&mut runtime, config),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn stop_http_server(state: tauri::State<'_, crate::AppState>) -> CommandEnvelope<()> {
    match state.http_server.lock() {
        Ok(mut runtime) => stop_http_server_command(&mut runtime),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn get_http_server_status(
    state: tauri::State<'_, crate::AppState>,
) -> CommandEnvelope<LocalServerStatus> {
    match state.http_server.lock() {
        Ok(runtime) => get_http_server_status_command(&runtime),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn start_mqtt_broker(
    state: tauri::State<'_, crate::AppState>,
    config: MqttBrokerConfig,
) -> CommandEnvelope<MqttBrokerStatus> {
    match state.mqtt_broker.lock() {
        Ok(mut runtime) => start_mqtt_broker_command(&mut runtime, config),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn stop_mqtt_broker(state: tauri::State<'_, crate::AppState>) -> CommandEnvelope<()> {
    match state.mqtt_broker.lock() {
        Ok(mut runtime) => stop_mqtt_broker_command(&mut runtime),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(feature = "desktop")]
#[tauri::command]
pub fn get_mqtt_broker_status(
    state: tauri::State<'_, crate::AppState>,
) -> CommandEnvelope<MqttBrokerStatus> {
    match state.mqtt_broker.lock() {
        Ok(runtime) => get_mqtt_broker_status_command(&runtime),
        Err(err) => CommandEnvelope::error("server_lock", err.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn starts_stops_and_reports_http_server_status() {
        let mut runtime = HttpServerRuntime::default();
        let config = HttpServerConfig {
            host: "127.0.0.1".to_string(),
            port: 8080,
            serve_dir: PathBuf::from("/tmp/serve"),
            upload_dir: PathBuf::from("/tmp/upload"),
        };

        let started = start_http_server_command(&mut runtime, config).data.unwrap();
        assert!(started.running);
        assert_eq!(started.base_url, "http://127.0.0.1:8080");

        let status = get_http_server_status_command(&runtime).data.unwrap();
        assert!(status.http.unwrap().running);

        assert!(stop_http_server_command(&mut runtime).ok);
        let status = get_http_server_status_command(&runtime).data.unwrap();
        assert!(!status.http.unwrap().running);
    }

    #[test]
    fn starts_stops_and_reports_mqtt_broker_status() {
        let mut runtime = MqttBrokerRuntime::default();
        let config = MqttBrokerConfig {
            host: "127.0.0.1".to_string(),
            port: 1883,
        };

        let started = start_mqtt_broker_command(&mut runtime, config).data.unwrap();
        assert!(started.running);
        assert_eq!(started.bind, "127.0.0.1:1883");

        assert!(runtime.record_topic("mmwk/mmwk/device-1/device/cmd"));
        assert!(!runtime.record_topic("public/chat"));
        let status = get_mqtt_broker_status_command(&runtime).data.unwrap();
        assert_eq!(status.accepted_topics, 1);
        assert_eq!(status.rejected_topics, 1);

        assert!(stop_mqtt_broker_command(&mut runtime).ok);
        assert!(!get_mqtt_broker_status_command(&runtime).data.unwrap().running);
    }
}
