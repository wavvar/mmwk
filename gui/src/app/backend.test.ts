import { invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listServerProfiles } from "./backend";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn()
}));

describe("backend", () => {
  beforeEach(() => {
    vi.mocked(invoke).mockReset();
  });

  it("unwraps successful Tauri command envelopes", async () => {
    vi.mocked(invoke).mockResolvedValueOnce({
      ok: true,
      data: [
        {
          id: "srv-1",
          name: "Local bench",
          mqtt_host: "127.0.0.1",
          mqtt_port: 1883,
          http_host: "127.0.0.1",
          http_port: 8080,
          shared: true
        }
      ]
    });

    await expect(listServerProfiles()).resolves.toHaveLength(1);
    expect(invoke).toHaveBeenCalledWith("list_server_profiles", undefined);
  });
});
