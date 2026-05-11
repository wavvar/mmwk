import { invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listServerProfiles, startHttpServer, startMqttBroker } from "./backend";

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

  it("invokes embedded HTTP server commands", async () => {
    vi.mocked(invoke).mockResolvedValueOnce({
      ok: true,
      data: {
        running: true,
        base_url: "http://127.0.0.1:8080",
        served_requests: 0,
        uploads_received: 0
      }
    });

    await expect(
      startHttpServer({
        host: "127.0.0.1",
        port: 8080,
        serve_dir: "/tmp/serve",
        upload_dir: "/tmp/upload"
      })
    ).resolves.toMatchObject({ running: true });
    expect(invoke).toHaveBeenCalledWith("start_http_server", {
      config: {
        host: "127.0.0.1",
        port: 8080,
        serve_dir: "/tmp/serve",
        upload_dir: "/tmp/upload"
      }
    });
  });

  it("invokes scoped MQTT broker commands", async () => {
    vi.mocked(invoke).mockResolvedValueOnce({
      ok: true,
      data: {
        running: true,
        bind: "127.0.0.1:1883",
        active_clients: 0,
        accepted_topics: 0,
        rejected_topics: 0
      }
    });

    await expect(startMqttBroker({ host: "127.0.0.1", port: 1883 })).resolves.toMatchObject({
      running: true
    });
    expect(invoke).toHaveBeenCalledWith("start_mqtt_broker", {
      config: { host: "127.0.0.1", port: 1883 }
    });
  });
});
