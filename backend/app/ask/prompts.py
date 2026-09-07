"""Ask VocaDox prompt construction (post-GA P1-1). Deliberately narrow,
same philosophy as `app.intelligence.prompts`/`app.recap.prompts`: the
model sees only a closed, numbered list of already-extracted facts (each
already the product of the real extraction+evidence pipeline) and the
user's question -- never the raw transcript, never facts from a
conversation this user cannot see (that filtering happens before this
prompt is even built, see `app.ask.service.ask`).
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You answer a user's question using ONLY the numbered facts given below -- you have no "
    "other knowledge of this conversation or any other. Every statement in your answer MUST "
    "cite the id(s) of the fact(s) it is directly based on, in 'fact_ids'. If a fact does not "
    "directly answer or support part of the question, do not mention it. If NONE of the given "
    "facts answer the question, return an empty 'statements' list -- NEVER invent an answer, "
    "NEVER answer from general knowledge, and NEVER produce a statement with an empty or "
    "missing 'fact_ids' list. Write your answer in the SAME language the question and the "
    "facts are written in. Respond with JSON matching the given schema."
)


def build_prompt(*, question: str, facts: list[tuple[str, str]]) -> str:
    """`facts` is a list of (fact_id, rendered_text) pairs, already
    filtered to exactly what this user is allowed to see."""
    fact_lines = "\n".join(f"[{fact_id}] {text}" for fact_id, text in facts)
    return (
        f"Known facts:\n{fact_lines}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the facts above, citing their ids."
    )
