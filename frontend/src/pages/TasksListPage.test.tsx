import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import { TasksListPage } from "./TasksListPage";

function Location() { const location = useLocation(); return <output>{location.pathname}:{location.state?.tab}</output>; }
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(["tasks", { status: "open" }], [
    { id: "fixture-1", description: "Transkript prüfen", assignee: "Testperson", status: "open", source: "user_created", conversation_id: "fixture-conversation", due_date: null },
    { id: "fixture-2", description: "Dokumentation prüfen", assignee: null, status: "open", source: "ai_extracted", conversation_id: "fixture-conversation", due_date: null },
  ]);
  render(<QueryClientProvider client={client}><MemoryRouter><TasksListPage/><Location/></MemoryRouter></QueryClientProvider>);
}
describe("task search", () => {
  it("filters by description or assignee without inventing results", () => {
    show();
    const input = screen.getByRole("textbox", { name: "Aufgaben suchen" });
    fireEvent.change(input, { target: { value: "TESTPERSON" } });
    expect(screen.getByText("Transkript prüfen")).toBeInTheDocument();
    expect(screen.queryByText("Dokumentation prüfen")).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: "unmatched" } });
    expect(screen.getByText("Keine passenden Aufgaben")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByText("Dokumentation prüfen")).toBeInTheDocument();
  });
  it("opens the conversation tasks tab", () => {
    show();
    fireEvent.click(screen.getByText("Transkript prüfen"));
    expect(screen.getByText("/app/conversations/fixture-conversation:tasks")).toBeInTheDocument();
  });
});
