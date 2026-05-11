use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Clone, Copy)]
pub struct MqttRoute<'a> {
    pub prod: &'a str,
    pub oid: &'a str,
    pub cid: &'a str,
    pub did: &'a str,
    pub include_raw_cmd: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MqttTopics {
    pub prod: String,
    pub oid: String,
    pub cid: String,
    pub did: String,
    pub cmd: String,
    pub resp: String,
    pub raw_data: String,
    pub raw_resp: String,
    pub raw_cmd: String,
    pub hub_inquiry: String,
    pub hub_config: String,
    pub stream_in: String,
    pub stream_ack: String,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum TopicError {
    #[error("{0} is required")]
    Required(&'static str),
    #[error("{0} must be a single MQTT topic segment")]
    InvalidSegment(&'static str),
}

pub fn derive_mqtt_topics(route: MqttRoute<'_>) -> Result<MqttTopics, TopicError> {
    let prod = segment("prod", route.prod, true)?;
    let oid = segment("oid", route.oid, true)?;
    let cid = segment("cid", route.cid, false)?;
    let did = segment("did", route.did, false)?;
    let topic_id = if cid.is_empty() { &did } else { &cid };

    if topic_id.is_empty() {
        return Err(TopicError::Required("cid or did"));
    }

    let prefix = format!("{prod}/{oid}/{topic_id}");
    let resp = format!("{prefix}/device/resp");

    Ok(MqttTopics {
        prod,
        oid,
        cid,
        did,
        cmd: format!("{prefix}/device/cmd"),
        raw_data: format!("{prefix}/raw/data"),
        raw_resp: format!("{prefix}/raw/resp"),
        raw_cmd: if route.include_raw_cmd {
            format!("{prefix}/raw/cmd")
        } else {
            String::new()
        },
        hub_inquiry: format!("{prefix}/hub/inquiry"),
        hub_config: format!("{prefix}/hub/config"),
        stream_in: format!("{prefix}/stream/in"),
        stream_ack: resp.clone(),
        resp,
    })
}

fn segment(
    name: &'static str,
    value: &str,
    required: bool,
) -> Result<String, TopicError> {
    let segment = value.trim();
    if segment.is_empty() {
        return if required {
            Err(TopicError::Required(name))
        } else {
            Ok(String::new())
        };
    }
    if segment.contains('/') || segment.contains('\0') {
        return Err(TopicError::InvalidSegment(name));
    }
    Ok(segment.to_string())
}
