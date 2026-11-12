# Noise and agreement

## Measure noise first

LLM judges don't give the same verdict every time. With one judge sample, a few
verdicts in a set of 15 to 20 cases can flip between identical runs, which can
move agreement by over 10 points with no change at all.

-   Before comparing two versions, run the current version twice.
-   Treat differences of one or two cases as noise.
-   Use 3 or more samples for the final check.

## Agreement

`scripts/agreement.py` compares metric scores with labels. A score and a label
agree when both are on the same side of the threshold. Use the metric's own
pass threshold everywhere: build the review page with it, and `agreement.py`
reads it from `labels.json` (default 0.5 only when the labels don't say). It
reports accuracy, Cohen's kappa (agreement corrected for chance), a confusion
table, results per pattern, and the list of disagreements.

## Label sets

When labels come from an existing autorater instead of people, keep two sets:

-   the verdicts as given;
-   a corrected set where the trajectory clearly contradicts a verdict, each
    change with a written reason.

Report agreement against both, and list every case that still needs a human
decision. Agreement with another autorater is not agreement with people.
