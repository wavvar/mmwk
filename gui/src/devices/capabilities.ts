export type DeviceProfile = "bridge" | "hub";
export type HubSidecar = "cli" | "care" | "rmaker";

export type DeviceCapabilityInput = {
  profile: DeviceProfile;
  sidecar?: HubSidecar;
};

export type CommandGroup =
  | "system"
  | "device"
  | "radar"
  | "collection"
  | "endpoint"
  | "hub"
  | "hub-events"
  | "care"
  | "rmaker";

const BASE_GROUPS: CommandGroup[] = [
  "system",
  "device",
  "radar",
  "collection",
  "endpoint"
];

export function visibleCommandGroups(device: DeviceCapabilityInput): CommandGroup[] {
  const groups = new Set<CommandGroup>(BASE_GROUPS);

  if (device.profile === "hub") {
    groups.add("hub");
    groups.add("hub-events");

    if (device.sidecar === "care") {
      groups.add("care");
    }
    if (device.sidecar === "rmaker") {
      groups.add("rmaker");
    }
  }

  return Array.from(groups);
}
