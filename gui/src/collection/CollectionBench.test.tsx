import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CollectionBench from "./CollectionBench";

describe("CollectionBench", () => {
  it("shows multi-device raw collection counters and controls", () => {
    render(<CollectionBench />);

    expect(screen.getByText("Raw Collection")).toBeTruthy();
    expect(screen.getByText("Bytes")).toBeTruthy();
    expect(screen.getByText("Messages")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy();
  });
});
