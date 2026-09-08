import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DocumentSection } from "../api/documents";
import { DocumentContent } from "./DocumentContent";

function freeformSections(text: string): DocumentSection[] {
  return [{ category: "__document_body__", title: null, statements: [{ text, fact_ids: [] }] }];
}

describe("DocumentContent freeform layout", () => {
  it("splits the aggregate statement into paragraphs on blank lines", () => {
    render(
      <DocumentContent
        sections={freeformSections("Erster Absatz.\n\nZweiter Absatz.\n\nDritter Absatz.")}
        layout="freeform"
      />
    );
    expect(screen.getByText("Erster Absatz.")).toBeInTheDocument();
    expect(screen.getByText("Zweiter Absatz.")).toBeInTheDocument();
    expect(screen.getByText("Dritter Absatz.")).toBeInTheDocument();
  });

  it("does not synthesize any salutation/closing chrome", () => {
    render(<DocumentContent sections={freeformSections("Nur mein eigener Text.")} layout="freeform" />);
    expect(screen.getByText("Nur mein eigener Text.")).toBeInTheDocument();
    expect(screen.queryByText(/Sehr geehrte/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Mit freundlichen/)).not.toBeInTheDocument();
  });

  it("reinterprets maxStatements as a paragraph limit and truncates", () => {
    render(
      <DocumentContent
        sections={freeformSections("Absatz eins.\n\nAbsatz zwei.\n\nAbsatz drei.")}
        layout="freeform"
        maxStatements={2}
      />
    );
    expect(screen.getByText("Absatz eins.")).toBeInTheDocument();
    expect(screen.getByText("Absatz zwei.")).toBeInTheDocument();
    expect(screen.queryByText("Absatz drei.")).not.toBeInTheDocument();
    expect(screen.getByText("…")).toBeInTheDocument();
  });

  it("shows every paragraph and no truncation marker when under the limit", () => {
    render(
      <DocumentContent
        sections={freeformSections("Nur ein Absatz.")}
        layout="freeform"
        maxStatements={5}
      />
    );
    expect(screen.getByText("Nur ein Absatz.")).toBeInTheDocument();
    expect(screen.queryByText("…")).not.toBeInTheDocument();
  });

  it("renders the empty state when there are no sections at all", () => {
    render(<DocumentContent sections={[]} layout="freeform" />);
    expect(screen.getByText("(Keine Fakten zum Zusammenstellen)")).toBeInTheDocument();
  });
});
