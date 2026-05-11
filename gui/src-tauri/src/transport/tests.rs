use std::time::Duration;

use serde_json::json;

use crate::{
    protocol::{
        cliv1::Cliv1Request,
        envelope::{Cliv1Frame, Cliv1Response},
    },
    transport::{
        mqtt::MqttTransportConfig,
        serial::SerialTransportConfig,
        CancellationFlag, DeviceTransport, TransportError, request_with_retries,
    },
};

struct ScriptedTransport {
    frames: Vec<Result<Cliv1Frame, TransportError>>,
    sent: Vec<u64>,
}

impl DeviceTransport for ScriptedTransport {
    fn exchange(
        &mut self,
        request: &Cliv1Request,
        _timeout: Duration,
    ) -> Result<Cliv1Frame, TransportError> {
        self.sent.push(request.seq);
        self.frames.remove(0)
    }
}

#[test]
fn retries_failed_operations_and_matches_response_sequence() {
    let mut transport = ScriptedTransport {
        frames: vec![
            Err(TransportError::Timeout),
            Ok(Cliv1Frame::Response(Cliv1Response {
                seq: 9,
                ok: true,
                result: Some(json!({"status": "ready"})),
                error: None,
            })),
        ],
        sent: Vec::new(),
    };
    let request = Cliv1Request::new(9, "node", Some("info"), json!({}));

    let response = request_with_retries(
        &mut transport,
        &request,
        2,
        Duration::from_millis(1),
        &CancellationFlag::default(),
    )
    .unwrap();

    assert_eq!(response.seq, 9);
    assert_eq!(transport.sent, vec![9, 9]);
}

#[test]
fn rejects_mismatched_response_sequence() {
    let mut transport = ScriptedTransport {
        frames: vec![Ok(Cliv1Frame::Response(Cliv1Response {
            seq: 10,
            ok: true,
            result: Some(json!({})),
            error: None,
        }))],
        sent: Vec::new(),
    };
    let request = Cliv1Request::new(9, "node", Some("info"), json!({}));

    let err = request_with_retries(
        &mut transport,
        &request,
        1,
        Duration::from_millis(1),
        &CancellationFlag::default(),
    )
    .unwrap_err();

    assert!(matches!(err, TransportError::Protocol(_)));
}

#[test]
fn stops_before_send_when_cancelled() {
    let mut transport = ScriptedTransport {
        frames: vec![Err(TransportError::Timeout)],
        sent: Vec::new(),
    };
    let cancel = CancellationFlag::default();
    cancel.cancel();
    let request = Cliv1Request::new(1, "node", Some("info"), json!({}));

    let err = request_with_retries(
        &mut transport,
        &request,
        1,
        Duration::from_millis(1),
        &cancel,
    )
    .unwrap_err();

    assert!(matches!(err, TransportError::Cancelled));
    assert!(transport.sent.is_empty());
}

#[test]
fn transport_configs_expose_serial_and_mqtt_routes() {
    let serial = SerialTransportConfig {
        port: "/dev/ttyUSB0".to_string(),
        baudrate: 921_600,
        reset_on_connect: false,
    };
    assert_eq!(serial.baudrate, 921_600);

    let mqtt = MqttTransportConfig {
        uri: "mqtt://127.0.0.1:1883".to_string(),
        prod: "Acme".to_string(),
        oid: "Org001".to_string(),
        cid: "VeABC123".to_string(),
        did: "dc5475c879c0".to_string(),
        include_raw_cmd: true,
        qos: 1,
    };
    let topics = mqtt.topics().unwrap();

    assert_eq!(topics.cmd, "Acme/Org001/VeABC123/device/cmd");
    assert_eq!(topics.resp, "Acme/Org001/VeABC123/device/resp");
    assert_eq!(topics.stream_in, "Acme/Org001/VeABC123/stream/in");
}
