import { describe, expect, it } from "vitest";
import { visibleCommandGroups } from "./capabilities";

describe("visibleCommandGroups", () => {
  it("keeps hub scene controls hidden for bridge devices", () => {
    const groups = visibleCommandGroups({ profile: "bridge" });

    expect(groups).toContain("device");
    expect(groups).toContain("radar");
    expect(groups).toContain("collection");
    expect(groups).not.toContain("hub");
  });

  it("shows scene and hub event groups for hub devices", () => {
    const groups = visibleCommandGroups({ profile: "hub" });

    expect(groups).toContain("hub");
    expect(groups).toContain("hub-events");
  });

  it("shows RFCare controls only for care sidecar devices", () => {
    expect(visibleCommandGroups({ profile: "hub", sidecar: "care" })).toContain("care");
    expect(visibleCommandGroups({ profile: "hub", sidecar: "rmaker" })).not.toContain("care");
    expect(visibleCommandGroups({ profile: "bridge" })).not.toContain("care");
  });

  it("shows RainMaker controls only for rmaker sidecar devices", () => {
    expect(visibleCommandGroups({ profile: "hub", sidecar: "rmaker" })).toContain("rmaker");
    expect(visibleCommandGroups({ profile: "hub", sidecar: "care" })).not.toContain("rmaker");
    expect(visibleCommandGroups({ profile: "bridge" })).not.toContain("rmaker");
  });
});
