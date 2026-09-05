import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DesignSystemPage } from "./DesignSystemPage";
import { ToastProvider } from "./Toast";

describe("DesignSystemPage", () => {
  it("renders the token sections", () => {
    render(
      <ToastProvider>
        <DesignSystemPage />
      </ToastProvider>
    );
    expect(screen.getByText("Colors")).toBeInTheDocument();
    expect(screen.getByText("Typography")).toBeInTheDocument();
    expect(screen.getByText("Buttons")).toBeInTheDocument();
    expect(screen.getByText("Form Controls")).toBeInTheDocument();
    expect(screen.getByText("Data Table")).toBeInTheDocument();
    expect(screen.getByText("Modal, Drawer & Toast")).toBeInTheDocument();
  });
});
