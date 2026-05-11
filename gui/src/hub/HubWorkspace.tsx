import CommandPanel from "../devices/CommandPanel";

type HubWorkspaceProps = {
  sidecar?: "cli" | "care" | "rmaker" | null;
};

export default function HubWorkspace({ sidecar }: HubWorkspaceProps) {
  return (
    <>
      <CommandPanel title="Node Inquiry" commands={["inquiry"]} />
      <CommandPanel title="Scene" commands={["read", "set", "apply", "wait"]} />
      <CommandPanel title="Hub Events" commands={["record", "pause", "replay", "export"]} />
      {sidecar === "care" ? (
        <CommandPanel title="RFCare" commands={["platform", "transfer", "room", "events"]} />
      ) : null}
      {sidecar === "rmaker" ? (
        <CommandPanel title="RainMaker" commands={["visibility", "claim", "status"]} />
      ) : null}
    </>
  );
}
