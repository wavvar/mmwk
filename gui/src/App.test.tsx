import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./app/backend", () => ({
  listDeviceProfiles: vi.fn().mockResolvedValue([]),
  listServerProfiles: vi.fn().mockResolvedValue([]),
  saveDeviceProfile: vi.fn()
}));

describe("App", () => {
  it("renders the MMWK desktop shell", () => {
    render(<App />);
    expect(screen.getByText("MMWK Desktop")).toBeTruthy();
  });
});
