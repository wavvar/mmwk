import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DeviceList from "./DeviceList";

vi.mock("../app/backend", () => ({
  listDeviceProfiles: vi.fn().mockResolvedValue([]),
  listServerProfiles: vi.fn().mockResolvedValue([
    {
      id: "srv-1",
      name: "Local bench",
      mqtt_host: "127.0.0.1",
      mqtt_port: 1883,
      http_host: "127.0.0.1",
      http_port: 8080,
      shared: true
    }
  ]),
  saveDeviceProfile: vi.fn()
}));

describe("DeviceList", () => {
  it("lets a new device select an existing shared server profile", async () => {
    render(<DeviceList />);

    await waitFor(() => {
      expect(screen.getByLabelText("Server Profile")).toBeTruthy();
    });

    const serverSelect = screen.getByLabelText("Server Profile") as HTMLSelectElement;
    expect(serverSelect.value).toBe("srv-1");
    expect(screen.getByText("Local bench")).toBeTruthy();
  });
});
