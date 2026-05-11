import CommandPanel from "../devices/CommandPanel";

export default function RadarWorkspace() {
  return (
    <>
      <CommandPanel title="Radar" commands={["status", "start", "stop"]} />
      <CommandPanel title="Raw" commands={["status", "config_get", "config_set", "start", "stop", "trigger"]} />
      <CommandPanel title="Record" commands={["start", "trigger", "stop"]} />
      <CommandPanel title="Stream" commands={["open", "status", "abort", "close"]} />
      <CommandPanel title="Collect" commands={["run"]} />
    </>
  );
}
