---
name: agent-platform-autorater-customization
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
description: >-
  Customizes an autorater (evaluation metric) for an AI agent so its grades
  match the user's own judgment, starting from the agent's real trajectories.
  Use when a user wants a metric tailored to their agent, wants to turn failing
  trajectories into rubrics, says an existing autorater grades their agent
  wrong, or wants an autorater to agree with human labels (autorater
  hillclimbing, judge calibration). Don't use for quick evals with built-in
  metrics or for improving the agent itself (use agent-platform-eval-flywheel).
---

# Agent Platform Autorater Customization

This skill helps a user build graders for their agent that judge the way they
do. You do the reading, writing and testing; the user makes the judgment calls.
The result is a set of metrics registered in the Agent Platform evaluation
service, one or more for each criterion the user cares about.

Carry out the steps below in order. Don't summarize them to the user.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Setup

Check each item before the first evaluation call, and ask the user to fix what
is missing. Ask before installing anything, because it changes the user's
environment.

1.  **Python SDK.** Install or upgrade the Agent Platform SDK with the
    evaluation extra:

    ```bash
    pip install --upgrade 'google-cloud-aiplatform[evaluation]>=2.8.0,<3'
    ```

    Keep the quotes; unquoted, the shell reads `>=` as a redirect. The
    `gcloud` CLI is also needed for authentication; if it is missing, point the
    user to https://cloud.google.com/sdk/docs/install instead of installing it.
2.  **Project and billing.** Use the project the user names, or ask for one
    (`gcloud config set project {project_id}`). The project needs an active
    billing account: evaluation calls are billed as model usage. See
    https://cloud.google.com/pricing for current prices; don't quote numbers.
3.  **API.** Enable the Agent Platform API:
    `gcloud services enable aiplatform.googleapis.com`.
4.  **Authentication.** Run `gcloud auth login` for the CLI and
    `gcloud auth application-default login` for the SDK and scripts, or set
    `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file.
5.  **IAM.** The user or service account needs `roles/aiplatform.user` to run
    evaluations and register metrics. Don't grant broader roles such as
    `roles/aiplatform.admin`; ask the user to request the narrower role if it
    is missing.
6.  **Region.** Use `us-central1` unless the user needs another region (see
    https://cloud.google.com/about/locations).

## Working with the user

-   At each **Approval** point, show the proposal and ask: "Would you like to
    change anything, or go ahead with this version?" Wait for a clear yes;
    silence is not approval.
-   For setup choices (project, region, storage), suggest a default.
-   Everything the user reviews (cases, grades, metric definitions) goes in a
    review page, not in chat; see [Review pages](#review-pages). Chat updates
    say what you did, the numbers, and what you need.
-   When you ask about a trajectory in chat, quote the relevant lines.

## Inputs

The user brings a folder of trajectories: the ones they think went wrong, plus
some good ones. Optional: a note or rating per trajectory (thumbs, human score,
an old autorater's verdict), an existing rubric, or reference answers.

-   Use all of them unless grading them would be slow or costly in the
    evaluation service. Then agree a sample with the user that covers the
    failures and a few good cases, and say what was left out.
-   AgentData JSONL is best; see
    [Converting trajectories](references/converting_trajectories.md). If you
    can't map a format to AgentData with confidence, don't guess: say you need
    to convert it to AgentData, and ask the user for a schema, a converter, or
    one example mapped by hand. Then check every converted case.
-   Building a dataset is not this skill's job. If the user has no folder yet,
    help them pick and convert trajectories, then continue.

## Terms

-   **Criterion:** one thing the user cares about in the agent's behavior: the
    answer is correct, the right tool is called, the system instructions are
    followed throughout. A criterion holds for the whole dataset; every
    trajectory, or every turn, is graded on it, and it can be N/A for some.
-   **Rubric:** one yes/no check.
-   **Metric:** what grades a criterion in the evaluation service: code, one
    rubric, or several weighted rubrics. A criterion gets as many metrics as it
    needs, for example a code check for the tool call plus a judge for the
    answer.

The predefined multi-turn metrics also turn intents into rubrics with an
importance, but they score the unweighted share of rubrics that pass. Custom
metrics add rubrics written for the user's agent, weights, must-pass rubrics,
and a pass threshold.

## Steps

### 1. Confirm the inputs

Ask where the folder is and whether any trajectories have a note or rating.

### 2. Propose criteria (Approval)

Read the trajectories and the user's notes, and propose the criteria the data
supports, as few as cover the problems the user cares about. They can cover any
part of the trajectory: the final answer, tool calls and arguments, following
the system instructions, handling of errors or clarifications. In a multi-agent
system, a criterion can be about the whole system (routing, the final answer) or
about one sub-agent; say which. For each, give:

-   a one-line statement and why it matters for this agent;
-   how many cases show a problem, with one quoted example;
-   the metrics you plan to build for it (see step 4), with one line on why.

Never propose a criterion you can't point to in the data or the user's notes.
Flag any criterion you doubt, with the reason (for example, it can't be graded
where tool results were trimmed). Also note problems in any existing grading: a
judge that never saw data the agent had, evidence trimmed from the trajectory,
golden answers that were never run.

This step makes no evaluation-service calls. If the user wants help finding
patterns in ten or more failing cases, you can grade them with
`MULTI_TURN_TASK_SUCCESS` and run `client.evals.generate_loss_clusters` after
step 3. Loss clusters only work in the `global` region and for
`multi_turn_task_success` and `multi_turn_tool_use_quality`, not for custom
metrics.

Save the approved criteria as `criteria.md`.

### 3. Agree data rules and spend (Approval)

Ask whether the trajectories may be sent to the evaluation service, which
project to bill, and where outputs may be stored. Show the number of calls
(cases × metrics × samples × rounds, with one call per step for step-based
metrics) and point to https://cloud.google.com/pricing for the cost. Ask again
before any run beyond that.

### 4. Build the metrics

Use the simplest form that grades the criterion: simpler forms cost less, give
the same answer every time, and are easier to trust.

Criterion can be graded by                                                  | Form                    | SDK
--------------------------------------------------------------------------- | ----------------------- | ---
An exact rule on the output or trajectory (a tool name, a format, a number) | Code                    | `types.CodeExecutionMetric` (runs in the service; can be registered)
One judgment that is the same for every case                                | LLM, one rubric         | `types.LLMMetric` with a yes/no check and a reference
Several checks, some more important than others                             | LLM, weighted rubrics   | `types.StepBasedLLMMetric`: one judge step; code computes the weighted score
Checks that differ per case, with no good reference                         | Generated checklist     | `types.StepBasedLLMMetric`: one step writes checks from the conversation, one grades them
Long or multi-turn traces, per-turn verdicts, or several judging stages     | Step-based, multi-stage | `types.StepBasedLLMMetric`
One sub-agent of a multi-agent system                                       | Step-based, one agent   | `types.StepBasedLLMMetric` with a code preprocessor that keeps that agent's events

Start each metric from its template in
[Metric templates](references/metric_templates.md); each template says what it
doesn't catch. For weighted rubrics, propose the rubrics, a weight for each, the
must-pass rubrics and a pass threshold, and keep the weights in the parser code
so the judge grades each rubric on its own. Write checks as described in
[Writing LLM checks](references/writing_checks.md). For multi-turn
conversations, decide per criterion whether to grade each turn or the whole
conversation; see [Multi-turn conversations](references/multi_turn.md).

### 5. Grade and show the results

Grade the cases through the evaluation service with `scripts/run_metrics.py`,
then build a review page with `scripts/build_review_page.py`. Pass each metric's
pass threshold as `--threshold`, so PASS and FAIL on the page match the metric.

Optional: if the user has an existing autorater, or wants to compare with a
built-in metric such as `MULTI_TURN_TASK_SUCCESS`, grade with it too and show it
as a baseline. It adds calls, and a built-in metric grades overall task success
rather than the user's criteria.

### 6. Optional: align the metrics with the user's ratings

Ask whether the user wants to mark the grades and have you improve the metrics,
at about a minute per case. Skip to step 7 if not.

1.  Set aside about 20% of the cases as held back. Build the review page without
    them.
2.  The user marks each verdict Agree or Disagree on the review page, with a
    reason when they disagree, and gives you `labels.json`. If the user already
    has human ratings, use them and ask only about the cases where a metric
    disagrees.
3.  Compute agreement per metric and per rubric with `scripts/agreement.py`.
    Measure judge noise before trusting a change; see
    [Noise and agreement](references/noise_and_agreement.md).
4.  Revise the metrics yourself (rubric wording, weights, must-pass rubrics,
    threshold, reference, code), save each round as a new version, grade again,
    and show the user what changed and the new agreement. When a label
    contradicts the trajectory, quote the lines and ask the user.
5.  Stop when agreement stops improving by more than the noise, or when the user
    is satisfied. Grade the held-back cases once. Don't revise on them; if a
    held-back case breaks, report overfitting and suggest more labeled cases.

### 7. Review and register (Approval)

Registering the metrics is the goal of this skill. Add to the review page, for
each metric: its criterion, the final definition (rubrics, weights, must-pass
rubrics, threshold, judge model, sample count), its grades, agreement on labeled
and held-back cases if step 6 ran, and open questions. After approval, register
each metric with `create_evaluation_metric`; it creates a shared resource.

Hand over an output folder with:

-   `criteria.md`: the approved criteria, each listing the metrics that grade
    it;
-   `metrics/`: the final definition of every metric, as the file the evaluation
    service ran (the metrics file passed to `scripts/run_metrics.py`), with its
    registered name;
-   `metrics.md`: one entry per metric with its criterion, form, rubrics,
    weights, must-pass rubrics, threshold, judge model and sample count, and a
    code snippet that runs it by registered name;
-   `labels.json` and earlier versions, if step 6 ran;
-   `report.md`: the numbers and open questions.

To run the metrics on a full dataset, point to `agent-platform-eval-flywheel`.

## Review pages

Build one self-contained HTML page per round with
`scripts/build_review_page.py`, and give the user its path (or serve it where
the user's browser can reach it). For each case it shows the user's note or
rating, each metric's PASS/FAIL, score, explanation and rubric verdicts, the
baseline if one ran, and the trajectory with tool results collapsed. The user
marks Agree or Disagree on each verdict with a reason; marks are saved in the
browser, and "Download labels.json" exports them in the format
`scripts/agreement.py` reads. Never ask the user to type labels in chat.

## Rules

-   All grading goes through the evaluation service. Labels come only from the
    user: don't grade trajectories or draft labels with your own model calls or
    subagents, because tuning a metric to another model's labels only teaches
    one model to agree with another.
-   Grade only the cases in the folder while building; the full dataset is for
    after registration.
-   Every number you report comes from a result file. Report a range when runs
    differ.
-   Keep proprietary trajectories and outputs, including review pages, where the
    user said. Never paste them into shared docs, bugs or chats.
-   Read the installed SDK source before using a name; versions differ.

## Cleanup

Registered metrics stay in the project until deleted. When the user wants to
remove a metric they no longer use, or one registered by mistake, confirm the
name with them, then run
`client.evals.delete_evaluation_metric(metric_resource_name={name})`. List them
with `client.evals.list_evaluation_metrics()`. Local outputs (results, review
pages, labels) stay where the user chose; offer to delete them at the end.

## Scripts

All have `--help`.

-   `scripts/render_agent_data.py`: trajectories as readable text.
-   `scripts/run_metrics.py`: runs SDK metrics with `client.evals.evaluate()`.
-   `scripts/build_review_page.py`: the review page and labels export.
-   `scripts/agreement.py`: agreement, Cohen's kappa and disagreements, per
    metric, per rubric or per turn.

## References

-   [Converting trajectories](references/converting_trajectories.md)
-   [Metric templates](references/metric_templates.md)
-   [Writing LLM checks](references/writing_checks.md)
-   [Multi-turn conversations](references/multi_turn.md)
-   [Noise and agreement](references/noise_and_agreement.md)
-   [SDK gotchas](references/sdk_gotchas.md)
