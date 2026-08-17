import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the home page at /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Phase 0 scaffold/)).toBeInTheDocument();
  });

  it("renders the design system route", () => {
    render(
      <MemoryRouter initialEntries={["/design-system"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Design System" })).toBeInTheDocument();
  });
});
