import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./app/backend", () => ({
  listDeviceProfiles: vi.fn().mockResolvedValue([]),
  listServerProfiles: vi.fn().mockResolvedValue([]),
  saveDeviceProfile: vi.fn(),
  getHttpServerStatus: vi.fn().mockResolvedValue({ http: null }),
  getMqttBrokerStatus: vi.fn().mockResolvedValue({
    running: false,
    bind: "127.0.0.1:0",
    active_clients: 0,
    accepted_topics: 0,
    rejected_topics: 0
  }),
  executeDeviceCommand: vi.fn().mockResolvedValue({ payload: {} })
}));

describe("App", () => {
  it("renders the MMWK desktop shell", () => {
    render(<App />);
    expect(screen.getByText("MMWK Desktop")).toBeTruthy();
  });
});
