use serde::{Deserialize, Serialize};

use crate::protocol::topics::{derive_mqtt_topics, MqttRoute, MqttTopics, TopicError};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MqttTransportConfig {
    pub uri: String,
    pub prod: String,
    pub oid: String,
    pub cid: String,
    pub did: String,
    pub include_raw_cmd: bool,
    pub qos: u8,
}

impl MqttTransportConfig {
    pub fn topics(&self) -> Result<MqttTopics, TopicError> {
        derive_mqtt_topics(MqttRoute {
            prod: &self.prod,
            oid: &self.oid,
            cid: &self.cid,
            did: &self.did,
            include_raw_cmd: self.include_raw_cmd,
        })
    }
}
