use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MqttBrokerConfig {
    pub host: String,
    pub port: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MqttBrokerStatus {
    pub running: bool,
    pub bind: String,
    pub active_clients: u64,
    pub accepted_topics: u64,
    pub rejected_topics: u64,
}

#[derive(Debug, Default)]
pub struct MqttBrokerRuntime {
    config: Option<MqttBrokerConfig>,
    running: bool,
    active_clients: u64,
    accepted_topics: u64,
    rejected_topics: u64,
}

impl MqttBrokerRuntime {
    pub fn start(&mut self, config: MqttBrokerConfig) -> MqttBrokerStatus {
        self.running = true;
        self.config = Some(config);
        self.status()
    }

    pub fn stop(&mut self) {
        self.running = false;
        self.active_clients = 0;
    }

    pub fn record_topic(&mut self, topic: &str) -> bool {
        let accepted = is_mmwk_topic(topic);
        if accepted {
            self.accepted_topics += 1;
        } else {
            self.rejected_topics += 1;
        }
        accepted
    }

    pub fn status(&self) -> MqttBrokerStatus {
        let bind = self
            .config
            .as_ref()
            .map(|config| format!("{}:{}", config.host, config.port))
            .unwrap_or_else(|| "127.0.0.1:0".to_string());
        MqttBrokerStatus {
            running: self.running,
            bind,
            active_clients: self.active_clients,
            accepted_topics: self.accepted_topics,
            rejected_topics: self.rejected_topics,
        }
    }
}

pub fn is_mmwk_topic(topic: &str) -> bool {
    let parts: Vec<&str> = topic.split('/').collect();
    match parts.as_slice() {
        [_, _, _, "device", "cmd" | "resp"] => true,
        [_, _, _, "raw", "data" | "resp"] => true,
        [_, _, _, "hub", "inquiry" | "config"] => true,
        ["D", _, _, _, _, "event" | "data_rx"] => true,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_mmwk_device_topics() {
        for topic in [
            "mmwk/mmwk/device-1/device/cmd",
            "mmwk/mmwk/device-1/device/resp",
            "mmwk/mmwk/device-1/raw/data",
            "mmwk/mmwk/device-1/raw/resp",
            "mmwk/mmwk/device-1/hub/inquiry",
            "mmwk/mmwk/device-1/hub/config",
            "D/care/home/room/device/event",
            "D/care/home/room/device/data_rx",
        ] {
            assert!(is_mmwk_topic(topic), "{topic} should be accepted");
        }

        for topic in [
            "public/chat",
            "mmwk/mmwk/device-1/raw/cmd/extra",
            "mmwk/mmwk/device-1/raw/unknown",
            "D/care/home/room/device/other",
            "$SYS/broker/clients",
        ] {
            assert!(!is_mmwk_topic(topic), "{topic} should be rejected");
        }
    }
}
