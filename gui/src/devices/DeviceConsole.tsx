import type { DeviceProfile, HubSidecar } from "./capabilities";
import CommandPanel from "./CommandPanel";
import HubWorkspace from "../hub/HubWorkspace";
import RadarWorkspace from "../radar/RadarWorkspace";

type DeviceConsoleProps = {
  profile: DeviceProfile;
  sidecar?: HubSidecar | null;
};

export default function DeviceConsole({ profile, sidecar }: DeviceConsoleProps) {
  return (
    <section className="workspace-panel console-panel" aria-label="Device console">
      <div className="panel-heading">
        <h3>Device Console</h3>
        <span>{profile}</span>
      </div>
      <div className="console-grid">
        <CommandPanel title="Node" commands={["info", "agent", "heartbeat", "reboot", "ota"]} />
        <CommandPanel title="Network" commands={["wifi", "4g", "priority", "ntp", "mqtt", "status"]} />
        <RadarWorkspace />
        {profile === "hub" ? <HubWorkspace sidecar={sidecar} /> : null}
      </div>
    </section>
  );
}
