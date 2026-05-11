use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::Write,
    path::PathBuf,
};

use serde::{Deserialize, Serialize};

use super::manifest::{RunArtifact, RunManifest};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawCaptureDevice {
    pub device_id: String,
    pub raw_data_topic: String,
    pub raw_resp_topic: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawCaptureConfig {
    pub run_id: String,
    pub output_dir: PathBuf,
    pub devices: Vec<RawCaptureDevice>,
}

#[derive(Debug, Default, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawCaptureCounters {
    pub data_messages: u64,
    pub data_bytes: u64,
    pub resp_messages: u64,
    pub resp_bytes: u64,
}

struct DeviceSink {
    config: RawCaptureDevice,
    data_path: PathBuf,
    resp_path: PathBuf,
    data_file: File,
    resp_file: File,
    counters: RawCaptureCounters,
}

pub struct RawCapture {
    config: RawCaptureConfig,
    sinks: Vec<DeviceSink>,
}

impl RawCapture {
    pub fn start(config: RawCaptureConfig) -> std::io::Result<Self> {
        fs::create_dir_all(&config.output_dir)?;
        let mut sinks = Vec::new();
        for device in &config.devices {
            let data_path = config
                .output_dir
                .join(format!("{}_raw_data.sraw", device.device_id));
            let resp_path = config
                .output_dir
                .join(format!("{}_raw_resp.log", device.device_id));
            sinks.push(DeviceSink {
                config: device.clone(),
                data_file: OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&data_path)?,
                resp_file: OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&resp_path)?,
                data_path,
                resp_path,
                counters: RawCaptureCounters::default(),
            });
        }

        Ok(Self { config, sinks })
    }

    pub fn ingest(&mut self, topic: &str, payload: &[u8]) -> std::io::Result<bool> {
        for sink in &mut self.sinks {
            if topic == sink.config.raw_data_topic {
                sink.data_file.write_all(payload)?;
                sink.counters.data_messages += 1;
                sink.counters.data_bytes += payload.len() as u64;
                return Ok(true);
            }
            if sink.config.raw_resp_topic.as_deref() == Some(topic) {
                sink.resp_file.write_all(payload)?;
                sink.resp_file.write_all(b"\n")?;
                sink.counters.resp_messages += 1;
                sink.counters.resp_bytes += payload.len() as u64;
                return Ok(true);
            }
        }
        Ok(false)
    }

    pub fn counters(&self) -> BTreeMap<String, RawCaptureCounters> {
        self.sinks
            .iter()
            .map(|sink| (sink.config.device_id.clone(), sink.counters.clone()))
            .collect()
    }

    pub fn finish(mut self, interrupted: bool) -> std::io::Result<RunManifest> {
        for sink in &mut self.sinks {
            sink.data_file.flush()?;
            sink.resp_file.flush()?;
        }

        let mut artifacts = Vec::new();
        for sink in &self.sinks {
            artifacts.push(RunArtifact {
                device_id: sink.config.device_id.clone(),
                kind: "raw_data".to_string(),
                path: sink.data_path.clone(),
                bytes: sink.counters.data_bytes,
                messages: sink.counters.data_messages,
            });
            artifacts.push(RunArtifact {
                device_id: sink.config.device_id.clone(),
                kind: "raw_resp".to_string(),
                path: sink.resp_path.clone(),
                bytes: sink.counters.resp_bytes,
                messages: sink.counters.resp_messages,
            });
        }

        let manifest = RunManifest {
            run_id: self.config.run_id.clone(),
            interrupted,
            artifacts,
        };
        let manifest_path = self.config.output_dir.join("manifest.json");
        fs::write(
            manifest_path,
            serde_json::to_vec_pretty(&manifest).expect("manifest serializes"),
        )?;
        Ok(manifest)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "mmwk-gui-raw-{}-{}",
            std::process::id(),
            name
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn captures_raw_data_and_resp_across_devices() {
        let output_dir = temp_dir("multi");
        let mut capture = RawCapture::start(RawCaptureConfig {
            run_id: "run-1".to_string(),
            output_dir: output_dir.clone(),
            devices: vec![
                RawCaptureDevice {
                    device_id: "dev-a".to_string(),
                    raw_data_topic: "mmwk/mmwk/a/raw/data".to_string(),
                    raw_resp_topic: Some("mmwk/mmwk/a/raw/resp".to_string()),
                },
                RawCaptureDevice {
                    device_id: "dev-b".to_string(),
                    raw_data_topic: "mmwk/mmwk/b/raw/data".to_string(),
                    raw_resp_topic: None,
                },
            ],
        })
        .unwrap();

        assert!(capture.ingest("mmwk/mmwk/a/raw/data", b"\x01\x02").unwrap());
        assert!(capture.ingest("mmwk/mmwk/a/raw/resp", b"CMD READY").unwrap());
        assert!(capture.ingest("mmwk/mmwk/b/raw/data", b"\x03").unwrap());
        assert!(!capture.ingest("mmwk/mmwk/c/raw/data", b"\x04").unwrap());

        let counters = capture.counters();
        assert_eq!(counters["dev-a"].data_bytes, 2);
        assert_eq!(counters["dev-a"].resp_messages, 1);
        assert_eq!(counters["dev-b"].data_messages, 1);

        let manifest = capture.finish(false).unwrap();
        assert!(!manifest.interrupted);
        assert_eq!(fs::read(output_dir.join("dev-a_raw_data.sraw")).unwrap(), b"\x01\x02");
        assert_eq!(fs::read(output_dir.join("dev-b_raw_data.sraw")).unwrap(), b"\x03");
        assert!(output_dir.join("manifest.json").exists());
    }

    #[test]
    fn records_interrupted_manifest() {
        let output_dir = temp_dir("interrupted");
        let capture = RawCapture::start(RawCaptureConfig {
            run_id: "run-2".to_string(),
            output_dir,
            devices: vec![RawCaptureDevice {
                device_id: "dev-a".to_string(),
                raw_data_topic: "mmwk/mmwk/a/raw/data".to_string(),
                raw_resp_topic: None,
            }],
        })
        .unwrap();

        let manifest = capture.finish(true).unwrap();

        assert!(manifest.interrupted);
    }
}
