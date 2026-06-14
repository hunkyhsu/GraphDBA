import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock, Radio, RefreshCw, XCircle } from "lucide-react";

import { approveRun, getRun, type LoginResponse, type RunStateResponse } from "../../lib/api";
import { titleCase } from "../../lib/format";

type RunPageProps = {
  session: LoginResponse;
  runId: string;
};

const stages = [
  { key: "diagnosed", label: "Diagnostic" },
  { key: "validated_success", label: "Validation" },
  { key: "planned", label: "Planning" },
];

function CodeBlock({ value }: { value: string }) {
  return (
    <pre className="overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-900">
      <code>{value}</code>
    </pre>
  );
}

export function RunPage({ session, runId }: RunPageProps) {
  const [run, setRun] = useState<RunStateResponse | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function loadRun() {
    setIsLoading(true);
    setError("");
    getRun(runId, session.access_token)
      .then(setRun)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Failed to load run."))
      .finally(() => setIsLoading(false));
  }

  useEffect(loadRun, [runId, session.access_token]);

  const currentIndex = useMemo(() => {
    const status = run?.values.workflow_status;
    return stages.findIndex((stage) => stage.key === status);
  }, [run]);

  const alert = run?.values.alert;
  const plan = run?.values.final_plan;
  const isWaitingApproval = run?.values.workflow_status === "planned";

  async function submitDecision(decision: "approved" | "rejected") {
    setIsSubmitting(true);
    setActionError("");
    try {
      await approveRun(runId, { decision, feedback: feedback || null }, session.access_token);
      loadRun();
    } catch (submitError) {
      setActionError(submitError instanceof Error ? submitError.message : "Failed to submit decision.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (error) {
    return <div className="px-5 pb-8 sm:px-8"><div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div></div>;
  }

  return (
    <div className="grid gap-6 px-5 pb-8 sm:px-8 xl:grid-cols-[360px_1fr_380px]">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-950">Workflow Timeline</h2>
        <div className="mt-6 space-y-5">
          {stages.map((stage, index) => {
            const isDone = currentIndex > -1 && index < currentIndex;
            const isCurrent = index === currentIndex;
            return (
              <div key={stage.key} className="flex gap-4">
                <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-semibold ${
                  isDone ? "bg-emerald-600 text-white" : isCurrent ? "bg-amber-500 text-white" : "bg-slate-200 text-slate-500"
                }`}>
                  {isDone ? <CheckCircle2 size={18} /> : index + 1}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-950">{stage.label}</p>
                  <p className={`mt-1 text-sm ${isDone ? "text-emerald-600" : isCurrent ? "text-amber-600" : "text-slate-500"}`}>
                    {isDone ? "Completed" : isCurrent ? "Current" : "Pending"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex gap-6 text-sm font-semibold text-slate-500">
            <span className="text-indigo-600">Plan Output</span>
            <span>Event Log</span>
            <span>Status View</span>
            <span>MCP Calls</span>
          </div>
          <button type="button" onClick={loadRun} className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50">
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
        <div className="space-y-5 p-5">
          {isLoading ? <div className="h-80 rounded-lg bg-slate-50" /> : (
            <>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm font-semibold text-slate-950">Run Summary</p>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  <div><dt className="text-slate-500">Alert</dt><dd className="font-semibold text-slate-900">{alert?.alertname ?? alert?.name ?? "-"}</dd></div>
                  <div><dt className="text-slate-500">Instance</dt><dd className="font-semibold text-slate-900">{alert?.instance ?? "-"}</dd></div>
                  <div><dt className="text-slate-500">Status</dt><dd className="font-semibold text-slate-900">{titleCase(run?.values.workflow_status)}</dd></div>
                  <div><dt className="text-slate-500">Attempt</dt><dd className="font-semibold text-slate-900">{run?.values.attempt_count ?? 0}</dd></div>
                </dl>
              </div>

              {plan ? (
                <div>
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold text-slate-950">Plan</h2>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{plan.change_reason}</p>
                  <div className="mt-4 space-y-3">
                    {plan.execution_steps.map((step) => (
                      <div key={step.step_order} className="grid gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[44px_1fr]">
                        <div className="grid h-10 w-10 place-items-center rounded-md border border-slate-200 bg-white font-semibold">{step.step_order}</div>
                        <CodeBlock value={step.action_sql} />
                      </div>
                    ))}
                  </div>
                </div>
              ) : <p className="text-sm text-slate-500">No execution plan has been generated yet.</p>}

              <div>
                <h3 className="text-sm font-semibold text-slate-950">Validation Evidence</h3>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {run?.values.current_hypotheses.length ? run.values.current_hypotheses.map((hypothesis, index) => (
                    <div key={String(hypothesis.id ?? index)} className="rounded-lg border border-slate-200 p-3 text-sm">
                      <CheckCircle2 className="text-emerald-600" size={18} />
                      <p className="mt-2 font-semibold text-slate-900">{String(hypothesis.root_cause ?? "Hypothesis")}</p>
                      <p className="mt-1 text-slate-500">{titleCase(String(hypothesis.status ?? "pending"))}</p>
                    </div>
                  )) : <p className="text-sm text-slate-500">Evidence will appear after validation.</p>}
                </div>
              </div>
            </>
          )}
        </div>
      </section>

      <aside className="space-y-5">
        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-950"><Clock size={18} /> Rollback Plan</h2>
          <div className="mt-4">
            {plan?.rollback_sql ? <CodeBlock value={plan.rollback_sql} /> : <p className="text-sm text-slate-500">{plan?.rollback_note ?? "No rollback plan yet."}</p>}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-950"><Radio size={18} /> Live Events</h2>
          <p className="mt-2 text-sm text-slate-500">SSE stream is available from the run endpoint when the backend server is running.</p>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">Human Feedback</h2>
          <textarea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="Optional comments for the execution plan..."
            className="mt-3 min-h-36 w-full rounded-md border border-slate-300 p-3 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
          />
          {actionError ? <p className="mt-2 text-sm text-red-600">{actionError}</p> : null}
          {run?.values.failure_reason ? <p className="mt-2 text-sm text-red-600">{run.values.failure_reason}</p> : null}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              disabled={!isWaitingApproval || isSubmitting || !feedback.trim()}
              onClick={() => submitDecision("rejected")}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-red-500 font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <XCircle size={18} /> Reject
            </button>
            <button
              type="button"
              disabled={!isWaitingApproval || isSubmitting}
              onClick={() => submitDecision("approved")}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-emerald-600 font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <CheckCircle2 size={18} /> Approve & Execute
            </button>
          </div>
        </section>
      </aside>
    </div>
  );
}
