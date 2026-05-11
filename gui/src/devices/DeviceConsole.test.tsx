import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import DeviceConsole from "./DeviceConsole";

afterEach(() => {
  cleanup();
});

describe("DeviceConsole", () => {
  it("shows bridge command groups", () => {
    render(<DeviceConsole profile="bridge" />);

    for (const label of [
      "Node",
      "Network",
      "Radar",
      "Raw",
      "Record",
      "Stream",
      "Collect"
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.queryByText("Scene")).toBeNull();
  });

  it("shows hub scene, inquiry, events, and sidecar controls", () => {
    render(<DeviceConsole profile="hub" sidecar="care" />);

    expect(screen.getByText("Node Inquiry")).toBeTruthy();
    expect(screen.getByText("Scene")).toBeTruthy();
    expect(screen.getByText("Hub Events")).toBeTruthy();
    expect(screen.getByText("RFCare")).toBeTruthy();
  });

  it("keeps RainMaker controls separate from RFCare", () => {
    render(<DeviceConsole profile="hub" sidecar="rmaker" />);

    expect(screen.getByText("RainMaker")).toBeTruthy();
    expect(screen.queryByText("RFCare")).toBeNull();
  });
});
