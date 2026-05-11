import { useEffect, useState } from "react";
import {
  listDeviceProfiles,
  listServerProfiles,
  saveDeviceProfile,
  type DeviceProfile,
  type ServerProfile
} from "../app/backend";
import DeviceEditor from "./DeviceEditor";

export default function DeviceList() {
  const [devices, setDevices] = useState<DeviceProfile[]>([]);
  const [servers, setServers] = useState<ServerProfile[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([listDeviceProfiles(), listServerProfiles()])
      .then(([loadedDevices, loadedServers]) => {
        if (!cancelled) {
          setDevices(loadedDevices);
          setServers(loadedServers.filter((server) => server.shared));
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(profile: DeviceProfile) {
    const saved = await saveDeviceProfile(profile);
    setDevices((current) => [
      ...current.filter((device) => device.id !== saved.id),
      saved
    ]);
  }

  return (
    <section className="workspace-panel" aria-label="Device profiles">
      <div className="panel-heading">
        <h3>Device Profiles</h3>
        <span>{devices.length} configured</span>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <DeviceEditor
        key={servers.map((server) => server.id).join(":")}
        servers={servers}
        onSave={handleSave}
      />
      <div className="table-list" role="list">
        {devices.map((device) => (
          <div className="table-row" key={device.id} role="listitem">
            <strong>{device.name || device.id}</strong>
            <span>{device.profile}</span>
            <span>{device.transport}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
