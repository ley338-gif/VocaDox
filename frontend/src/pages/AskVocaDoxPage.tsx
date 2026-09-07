import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { ask, type AskAnswer } from "../api/ask";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { TextInput } from "../design-system/FormControls";
import { EmptyState, ErrorState } from "../design-system/States";
import styles from "./AskVocaDoxPage.module.css";

/**
 * Post-GA P1-1: chat over the whole conversation history, with enforced
 * citation — every statement in an answer is technically only ever
 * formulated from a real, evidence-linked `ExtractedFact`; anything
 * without a real citation is discarded server-side before it ever
 * reaches this page (see backend app.ask.service.ask), never generated
 * here or hidden-then-shown.
 */
export function AskVocaDoxPage() {
  const { csrfToken } = useAuth();
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<AskAnswer[]>([]);

  const askMutation = useMutation({
    mutationFn: () => ask(question, null, csrfToken ?? ""),
    onSuccess: (answer) => {
      setHistory((prev) => [answer, ...prev]);
      setQuestion("");
    },
  });

  return (
    <div>
      <h1 style={{ fontSize: "var(--font-h1-size)", marginBottom: "var(--space-2)" }}>
        Ask VocaDox
      </h1>
      <p className={styles.disclosure}>
        <Sparkles size={13} aria-hidden="true" /> Antworten stammen ausschließlich aus bereits
        extrahierten, belegten Fakten Ihrer Gespräche — nie aus allgemeinem Wissen. Findet sich
        kein Beleg, bleibt die Antwort leer statt erfunden.
      </p>

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (question.trim()) askMutation.mutate();
        }}
      >
        <TextInput
          placeholder="Frage stellen…"
          aria-label="Frage stellen"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button
          variant="primary"
          type="submit"
          disabled={askMutation.isPending || !question.trim()}
        >
          {askMutation.isPending ? "Fragt…" : "Fragen"}
        </Button>
      </form>

      {askMutation.isError && (
        <ErrorState message="Frage konnte nicht beantwortet werden." />
      )}

      <div className={styles.history}>
        {history.length === 0 && !askMutation.isPending && (
          <EmptyState
            icon={<Sparkles size={20} aria-hidden="true" />}
            title="Noch keine Frage gestellt"
            description="Stellen Sie eine Frage zu Ihren Gesprächen — z. B. 'Welche Entscheidungen wurden diese Woche getroffen?'"
          />
        )}
        {history.map((answer) => (
          <Card key={answer.id}>
            <p className={styles.question}>{answer.question}</p>
            {answer.statements.length === 0 ? (
              <p className={styles.noEvidence}>
                {answer.had_candidate_evidence
                  ? "Keine der gefundenen Aussagen ließ sich eindeutig belegen."
                  : "Keine belegten Fakten zu dieser Frage gefunden."}
              </p>
            ) : (
              <ul className={styles.statementList}>
                {answer.statements.map((statement, index) => (
                  <li key={index} className={styles.statement}>
                    <p>{statement.text}</p>
                    <div className={styles.citations}>
                      {statement.citations.map((citation) => (
                        <button
                          key={citation.fact_id}
                          type="button"
                          className={styles.citationLink}
                          onClick={() => navigate(`/app/conversations/${citation.conversation_id}`, {
                            state: { tab: "facts" },
                          })}
                        >
                          {citation.conversation_title || "Gespräch"}
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
