import type { DeviceProfile, HubSidecar } from "./capabilities";
import CommandPanel from "./CommandPanel";
import HubWorkspace from "../hub/HubWorkspace";
import RadarWorkspace from "../radar/RadarWorkspace";

type DeviceConsoleProps = {
  deviceProfileId?: string | null;
  profile: DeviceProfile;
  sidecar?: HubSidecar | null;
};

function command(profile: DeviceProfile, service: string, action: string, destructive = false) {
  return {
    label: action,
    commandId: `${profile}/${service}/${action}`,
    destructive
  };
}

export default function DeviceConsole({ deviceProfileId, profile, sidecar }: DeviceConsoleProps) {
  return (
    <section className="workspace-panel console-panel" aria-label="Device console">
      <div className="panel-heading">
        <h3>Device Console</h3>
        <span>{profile}</span>
      </div>
      <div className="console-grid">
        <CommandPanel
          deviceProfileId={deviceProfileId}
          title="Node"
          commands={[
            command(profile, "node", "info"),
            command(profile, "node", "agent"),
            command(profile, "node", "heartbeat"),
            command(profile, "node", "reboot", true),
            command(profile, "node", "ota", true)
          ]}
        />
        <CommandPanel
          deviceProfileId={deviceProfileId}
          title="Network"
          commands={[
            command(profile, "network", "wifi", true),
            command(profile, "network", "4g", true),
            command(profile, "network", "priority", true),
            command(profile, "network", "ntp"),
            command(profile, "network", "mqtt", true),
            command(profile, "network", "status")
          ]}
        />
        <RadarWorkspace deviceProfileId={deviceProfileId} profile={profile} />
        {profile === "hub" ? (
          <HubWorkspace deviceProfileId={deviceProfileId} sidecar={sidecar} />
        ) : null}
      </div>
    </section>
  );
}
