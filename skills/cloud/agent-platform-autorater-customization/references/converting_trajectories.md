# Converting trajectories

Convert every source to the evaluation service's `AgentData` shape, so the
metrics and scripts work the same way for all sources.

## Sources

Source                       | How to load
---------------------------- | -----------
Local or Cloud Storage files | Read JSONL directly; ADK eval sets with `types.EvaluationDataset.load_from_adk_eval_set`
Cloud Trace                  | `client.evals.import_evaluation_set` with `cloud_trace_source` (filter with `trace_ids` or `session_ids`)
Interactions                 | `types.InteractionsDataSource`

Reading trajectories is read-only. Importing them into an evaluation set creates
a resource, so ask first.

## Shape

-   One `ConversationTurn` per agent call. When a user (real or simulated)
    answers a clarifying question, that is a new turn of the same user request.
    Keep the request-to-turn mapping in `turn_id`.
-   Tool calls become `function_call` parts. Their outputs become
    `function_response` parts with the rows or payload. When truncating, keep
    the start and the end, not only the start: time series keep their newest
    points at the end.
-   Mark internal reasoning as `thought=True`, so judges and preprocessors can
    drop it.
-   Convert typed values (for example timestamps stored as epoch numbers) to a
    readable form.
-   Put the golden answer, golden query and golden result rows in `reference`.
-   Keep extra fields a code metric or `--trajectory_response` needs (a
    rendered trajectory, the intended tool) as extra `EvalCase` attributes.
    Judge templates can't rely on them after registration (see
    `sdk_gotchas.md`).

## Check the conversion

Check with code, for every case:

-   every tool call and result is present;
-   text, queries and answers match the source exactly;
-   for multi-turn: user text, turn ids, and one reference section per user
    turn;
-   `types.EvalCase(**case)` validates.
