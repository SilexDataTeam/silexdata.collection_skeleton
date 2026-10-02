// SPDX-FileCopyrightText: Silex Data Solutions
// SPDX-License-Identifier: Apache-2.0
//
// Decide which of a workflow's runs for one commit to take the artifact from.
//
// One commit can have several runs of the same workflow: a re-push or a PR
// base change starts a second run, and the workflow's concurrency group
// cancels the first. Both can share a created_at to the second, so the API's
// newest-first order does not reliably put the surviving run first. A run
// that was cancelled or skipped therefore never decides the outcome while
// another run for the commit can.

"use strict";

const SUPERSEDED = new Set(["cancelled", "skipped"]);

function newestFirst(a, b) {
  if (a.created_at !== b.created_at) {
    return a.created_at < b.created_at ? 1 : -1;
  }
  return b.id - a.id;
}

// Returns {action, run}: "use" a successful run, "wait" for one still going
// (or for the first run to appear, with run undefined), or "fail" on the run
// that settled the outcome.
function selectRun(runs) {
  const sorted = [...runs].sort(newestFirst);
  const done = sorted.filter((run) => run.status === "completed");

  const success = done.find((run) => run.conclusion === "success");
  if (success) {
    return { action: "use", run: success };
  }
  const pending = sorted.find((run) => run.status !== "completed");
  if (pending || sorted.length === 0) {
    return { action: "wait", run: pending };
  }
  const settled = done.find((run) => !SUPERSEDED.has(run.conclusion));
  return { action: "fail", run: settled || done[0] };
}

module.exports = { selectRun };
