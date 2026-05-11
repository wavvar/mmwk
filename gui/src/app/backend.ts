import { invoke } from "@tauri-apps/api/core";

export type BackendError = {
  code: string;
  message: string;
};

export type CommandEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: BackendError;
};

export type DeviceProfile = {
  id: string;
  name: string;
  profile: "bridge" | "hub";
  board?: string | null;
  transport: "serial" | "mqtt";
  serial_port?: string | null;
  baudrate?: number | null;
  mqtt_server_profile_id?: string | null;
  mqtt_prod: string;
  mqtt_oid: string;
  mqtt_cid?: string | null;
  mqtt_did?: string | null;
  sidecar?: "cli" | "care" | "rmaker" | null;
};

export type ServerProfile = {
  id: string;
  name: string;
  mqtt_host: string;
  mqtt_port: number;
  http_host: string;
  http_port: number;
  shared: boolean;
};

async function call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const envelope = await invoke<CommandEnvelope<T>>(command, args);
  if (!envelope.ok) {
    const message = envelope.error?.message ?? `${command} failed`;
    throw new Error(message);
  }
  return envelope.data as T;
}

export function listDeviceProfiles(): Promise<DeviceProfile[]> {
  return call<DeviceProfile[]>("list_device_profiles");
}

export function saveDeviceProfile(profile: DeviceProfile): Promise<DeviceProfile> {
  return call<DeviceProfile>("save_device_profile", { profile });
}

export function deleteDeviceProfile(id: string): Promise<void> {
  return call<void>("delete_device_profile", { id });
}

export function listServerProfiles(): Promise<ServerProfile[]> {
  return call<ServerProfile[]>("list_server_profiles");
}

export function saveServerProfile(profile: ServerProfile): Promise<ServerProfile> {
  return call<ServerProfile>("save_server_profile", { profile });
}

export function deleteServerProfile(id: string): Promise<void> {
  return call<void>("delete_server_profile", { id });
}
