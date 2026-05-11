import { useEffect, useState } from "react";
import { listServerProfiles, type ServerProfile } from "../app/backend";

export default function ServerProfiles() {
  const [servers, setServers] = useState<ServerProfile[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listServerProfiles()
      .then((profiles) => {
        if (!cancelled) {
          setServers(profiles);
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

  return (
    <section className="workspace-panel" aria-label="Server profiles">
      <div className="panel-heading">
        <h3>Shared Servers</h3>
        <span>{servers.length} available</span>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="table-list" role="list">
        {servers.map((server) => (
          <div className="table-row" key={server.id} role="listitem">
            <strong>{server.name}</strong>
            <span>
              MQTT {server.mqtt_host}:{server.mqtt_port}
            </span>
            <span>
              HTTP {server.http_host}:{server.http_port}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
