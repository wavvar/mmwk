use std::collections::BTreeMap;

use serde::Serialize;

use crate::contracts::model::{ProtocolCoverage, ProtocolCoverageEntry};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CommandDescriptor {
    pub id: String,
    pub profile: String,
    pub sidecar: Option<String>,
    pub service: String,
    pub action: String,
    pub op: Option<String>,
    pub destructive: bool,
    pub restore: String,
    pub transports: Vec<String>,
    pub ui_group: String,
}

#[derive(Debug, Default)]
pub struct CommandRegistry {
    descriptors: BTreeMap<String, CommandDescriptor>,
}

impl CommandRegistry {
    pub fn from_coverages<'a>(
        coverages: impl IntoIterator<Item = &'a ProtocolCoverage>,
    ) -> CommandRegistry {
        let mut descriptors = BTreeMap::new();

        for coverage in coverages {
            for entry in &coverage.entries {
                let id = descriptor_id(entry);
                let descriptor = descriptors.entry(id.clone()).or_insert_with(|| {
                    CommandDescriptor {
                        id,
                        profile: entry.profile.clone(),
                        sidecar: entry.sidecar.clone(),
                        service: entry.service.clone(),
                        action: entry.action.clone(),
                        op: entry.op.clone(),
                        destructive: entry.destructive,
                        restore: entry.restore.clone(),
                        transports: Vec::new(),
                        ui_group: ui_group(entry),
                    }
                });

                if !descriptor.transports.contains(&entry.transport) {
                    descriptor.transports.push(entry.transport.clone());
                }
                descriptor.destructive |= entry.destructive;
                if descriptor.restore == "none" && entry.restore != "none" {
                    descriptor.restore = entry.restore.clone();
                }
            }
        }

        CommandRegistry { descriptors }
    }

    pub fn all(&self) -> impl Iterator<Item = &CommandDescriptor> {
        self.descriptors.values()
    }

    pub fn get(&self, id: &str) -> Option<&CommandDescriptor> {
        self.descriptors.get(id)
    }

    pub fn find(
        &self,
        profile: &str,
        sidecar: Option<&str>,
        service: &str,
        action: &str,
        op: Option<&str>,
    ) -> Option<&CommandDescriptor> {
        self.descriptors
            .get(&descriptor_key(profile, sidecar, service, action, op))
    }

    pub fn find_entry(&self, entry: &ProtocolCoverageEntry) -> Option<&CommandDescriptor> {
        self.descriptors.get(&descriptor_id(entry))
    }
}

fn descriptor_id(entry: &ProtocolCoverageEntry) -> String {
    descriptor_key(
        &entry.profile,
        entry.sidecar.as_deref(),
        &entry.service,
        &entry.action,
        entry.op.as_deref(),
    )
}

fn descriptor_key(
    profile: &str,
    sidecar: Option<&str>,
    service: &str,
    action: &str,
    op: Option<&str>,
) -> String {
    let mut key = String::from(profile);
    if let Some(sidecar) = sidecar.filter(|value| !value.is_empty()) {
        key.push(':');
        key.push_str(sidecar);
    }
    key.push('/');
    key.push_str(service);
    key.push('/');
    key.push_str(action);
    if let Some(op) = op.filter(|value| !value.is_empty()) {
        key.push('/');
        key.push_str(op);
    }
    key
}

fn ui_group(entry: &ProtocolCoverageEntry) -> String {
    if let Some(sidecar) = entry.sidecar.as_deref() {
        return sidecar.to_string();
    }

    match entry.service.as_str() {
        "help" | "proto" => "system",
        "node" | "network" => "device",
        "scene" => "hub",
        "stream" | "record" | "collect" | "radar.raw" => "collection",
        "endpoint" => "endpoint",
        service if service.starts_with("radar") => "radar",
        service => service,
    }
    .to_string()
}
