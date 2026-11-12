# Multi-turn conversations

## Agree two policies before labeling

Ask the user, with a recommendation:

-   **Carry-over:** "If a turn reuses an earlier turn's result instead of
    recomputing it, is that correct?" Code metrics need this answer.
-   **Mistakes carried forward:** "If a turn builds on an earlier wrong result,
    does that turn fail too?" LLM checks need this answer.

Without these answers, labels and metrics disagree on turns that are really
policy questions.

## Grade per user turn

-   One verdict per conversation can't be compared with per-turn labels. Use a
    step-based metric that returns a verdict per turn, or split the dataset into
    one case per turn (earlier turns condensed as context, only that turn's
    reference). A step-based metric needs one call per conversation instead of
    one per turn.
-   Make turn identity explicit. Mark each user message (`[USER TURN k]`) in a
    preprocessor and ask the judge to use that number. Line up the turn numbers
    across samples before voting; otherwise the vote can mix verdicts of
    different turns.
-   Try one judge step first. A two-step spec (notes per turn, then judge) did
    not do better in practice.
-   Predefined rubric metrics given generated rubrics did not work well on long
    conversations (parse failures, low agreement per turn). For per-case checks,
    use the generated-checklists template, which writes checks from every user
    turn, and trim long traces with a preprocessor.

## Look for two kinds of repeated failure

-   An early mistake carried into later turns.
-   The same mistake made fresh in each turn.

Both show up as several failing turns, but they need different fixes in the
agent.

## Check label consistency

Before tuning, check that the same situation is labeled the same way in
single-turn and multi-turn cases. If it isn't, no metric can match both; ask the
user which is right.

## Checking per-turn agreement

`scripts/agreement.py --turn_map metric=label_key` compares a per-turn label
list with per-turn verdicts parsed from the metric's explanation.
