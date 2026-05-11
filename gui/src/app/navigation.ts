export type WorkspaceRoute =
  | "devices"
  | "servers"
  | "console"
  | "collection"
  | "hub-events";

export const workspaceRoutes: Array<{ id: WorkspaceRoute; label: string }> = [
  { id: "devices", label: "Device Profiles" },
  { id: "servers", label: "Shared Servers" },
  { id: "console", label: "Device Console" },
  { id: "collection", label: "Collection Runs" },
  { id: "hub-events", label: "Hub Events" }
];
