import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DesignSystemPage } from "./DesignSystemPage";

describe("DesignSystemPage", () => {
  it("renders the token sections", () => {
    render(<DesignSystemPage />);
    expect(screen.getByText("Colors")).toBeInTheDocument();
    expect(screen.getByText("Typography")).toBeInTheDocument();
    expect(screen.getByText("Buttons")).toBeInTheDocument();
    expect(screen.getByText("Form Controls")).toBeInTheDocument();
  });
});
