import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DeviceConsole from "./DeviceConsole";
import { executeDeviceCommand } from "../app/backend";

vi.mock("../app/backend", () => ({
  executeDeviceCommand: vi.fn().mockResolvedValue({ payload: {} })
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
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

  it("executes a selected device command through the backend", () => {
    render(<DeviceConsole deviceProfileId="dev-1" profile="bridge" />);

    fireEvent.click(screen.getByRole("button", { name: "info" }));

    expect(executeDeviceCommand).toHaveBeenCalledWith({
      device_profile_id: "dev-1",
      command_id: "bridge/node/info",
      args: {},
      confirmation: undefined,
      key: undefined
    });
  });
});
