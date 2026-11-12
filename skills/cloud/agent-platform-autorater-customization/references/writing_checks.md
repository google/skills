# Writing LLM checks

-   Write checks as yes/no statements, never scales ("every number in the answer
    appears in a query result", not "rate accuracy 1-5"). Score 1 only if all
    checks pass.
-   Copy the label owner's definition when one exists: their checks, their
    tolerated differences, and which source wins when two disagree. Matching the
    owner's definition, and giving the judge the same evidence, are usually the
    biggest gains.
-   Give the judge the evidence the labels were made with. If labelers saw
    golden result rows, the judge needs them too, not only the golden query.
-   List tolerated differences explicitly: ordering, rounding, IDs vs names,
    extra columns, and outputs of steps that change between runs (such as LLM
    calls inside the agent).
-   Judges tend to side with the agent when the request is ambiguous. A blanket
    rule such as "treat the reference as the intended reading" fixes some cases
    but fails correct answers over small differences. What holds up better: the
    reference wins on facts (which table or column, the real date range) and on
    outcomes it computed; small method choices the user did not specify are
    tolerated.
-   Ask for JSON output with the checks first and the score last, so the judge
    reasons before it scores.
-   Don't mix concepts that have separate labels in one check (for example tool
    choice inside a "result is correct" check).
