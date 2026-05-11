import CommandPanel from "../devices/CommandPanel";

type HubWorkspaceProps = {
  deviceProfileId?: string | null;
  sidecar?: "cli" | "care" | "rmaker" | null;
};

function hubCommand(service: string, action: string, destructive = false) {
  return {
    label: action,
    commandId: `hub/${service}/${action}`,
    destructive
  };
}

export default function HubWorkspace({ deviceProfileId, sidecar }: HubWorkspaceProps) {
  return (
    <>
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Node Inquiry"
        commands={[hubCommand("node", "inquiry")]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Scene"
        commands={[
          hubCommand("scene", "read"),
          hubCommand("scene", "set", true),
          hubCommand("scene", "apply", true),
          hubCommand("scene", "wait")
        ]}
      />
      <CommandPanel
        deviceProfileId={deviceProfileId}
        title="Hub Events"
        commands={[
          { label: "record", commandId: "hub/events/record" },
          { label: "pause", commandId: "hub/events/pause" },
          { label: "replay", commandId: "hub/events/replay" },
          { label: "export", commandId: "hub/events/export" }
        ]}
      />
      {sidecar === "care" ? (
        <CommandPanel
          deviceProfileId={deviceProfileId}
          title="RFCare"
          commands={[
            { label: "platform", commandId: "hub:care/care.rfcare/rfc_web_realtime_contract" },
            { label: "transfer", commandId: "hub:care/care.rfcare/transfer_0x21_raw_data_rx", destructive: true },
            { label: "room", commandId: "hub:care/care.rfcare/wadar_scene_contract" },
            { label: "events", commandId: "hub/events/record" }
          ]}
        />
      ) : null}
      {sidecar === "rmaker" ? (
        <CommandPanel
          deviceProfileId={deviceProfileId}
          title="RainMaker"
          commands={[
            { label: "visibility", commandId: "hub:rmaker/rmaker/sidecar_contract" },
            { label: "claim", commandId: "hub:rmaker/rmaker/sidecar_contract" },
            { label: "status", commandId: "hub:rmaker/rmaker/sidecar_contract" }
          ]}
        />
      ) : null}
    </>
  );
}
