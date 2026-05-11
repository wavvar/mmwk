import CommandPanel from "../devices/CommandPanel";

type RadarWorkspaceProps = {
  deviceProfileId?: string | null;
  profile: "bridge" | "hub";
};

function command(profile: "bridge" | "hub", service: string, action: string, destructive = false) {
  return {
    label: action,
    commandId: `${profile}/${service}/${action}`,
    destructive
  };
}

export default function RadarWorkspace({ deviceProfileId, profile }: RadarWorkspaceProps) {
  return (
    <>
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Radar"
        commands={[
          command(profile, "radar", "status"),
          command(profile, "radar", "start", true),
          command(profile, "radar", "stop", true)
        ]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Raw"
        commands={[
          command(profile, "radar.raw", "status"),
          command(profile, "radar.raw", "config_get"),
          command(profile, "radar.raw", "config_set", true),
          command(profile, "radar.raw", "start", true),
          command(profile, "radar.raw", "stop", true),
          command(profile, "radar.raw", "trigger", true)
        ]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Record"
        commands={[
          command(profile, "record", "start", true),
          command(profile, "record", "trigger", true),
          command(profile, "record", "stop", true)
        ]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Stream"
        commands={[
          command(profile, "stream", "open", true),
          command(profile, "stream", "status"),
          command(profile, "stream", "abort"),
          command(profile, "stream", "close", true)
        ]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Collect"
        commands={[command(profile, "collect", "run", true)]}
      />
    </>
  );
}
