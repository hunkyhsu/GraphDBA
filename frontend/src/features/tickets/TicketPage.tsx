import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Edit3, Plus, Save, Trash2, XCircle } from "lucide-react";

import {
  approveRun,
  getTicketDetail,
  updateTicketPlan,
  type LoginResponse,
  type PlanStep,
  type TicketDetailResponse,
} from "../../lib/api";
import { formatDateTime, formatRelative, shortId, titleCase } from "../../lib/format";

type TicketPageProps = {
  session: LoginResponse;
  ticketId: string;
  mode: "detail" | "edit";
  onEdit: () => void;
  onSaved: (ticketId: string) => void;
  onOpenRun: (runId: string) => void;
};

function CodeBlock({ value }: { value: string }) {
  return (
    <pre className="overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-900">
      <code>{value}</code>
    </pre>
  );
}

function normalizeSteps(steps: PlanStep[]) {
  return steps.map((step, index) => ({
    step_order: step.step_order || index + 1,
    title: step.title ?? `Step ${index + 1}`,
    description: step.description ?? "",
    action_sql: step.action_sql,
  }));
}

export function TicketPage({ session, ticketId, mode, onEdit, onSaved, onOpenRun }: TicketPageProps) {
  const [ticket, setTicket] = useState<TicketDetailResponse | null>(null);
  const [steps, setSteps] = useState<PlanStep[]>([]);
  const [summary, setSummary] = useState("");
  const [rollbackSql, setRollbackSql] = useState("");
  const [humanNotes, setHumanNotes] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setError("");
    getTicketDetail(ticketId, session.access_token)
      .then((response) => {
        if (!isActive) return;
        setTicket(response);
        setSteps(normalizeSteps(response.proposed_steps));
        setSummary(response.change_reason);
        setRollbackSql(response.rollback_sql ?? "");
        const draft = response.metadata.draft as { human_notes?: string } | undefined;
        setHumanNotes(draft?.human_notes ?? "");
      })
      .catch((loadError) => {
        if (isActive) setError(loadError instanceof Error ? loadError.message : "Failed to load ticket.");
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });
    return () => {
      isActive = false;
    };
  }, [ticketId, session.access_token]);

  const runId = ticket?.run_id ?? ticket?.alert.thread_id ?? ticket?.alert_id;
  const canApprove = ticket?.status === "PENDING" && Boolean(runId);

  const rollbackLines = useMemo(() => {
    if (rollbackSql.trim()) return rollbackSql;
    return ticket?.rollback_note ?? "No rollback SQL is available for this plan.";
  }, [rollbackSql, ticket]);

  function updateStep(index: number, patch: Partial<PlanStep>) {
    setSteps((current) => current.map((step, stepIndex) => stepIndex === index ? { ...step, ...patch } : step));
  }

  function addStep() {
    setSteps((current) => [
      ...current,
      { step_order: current.length + 1, title: `Step ${current.length + 1}`, description: "", action_sql: "" },
    ]);
  }

  function removeStep(index: number) {
    setSteps((current) => current.filter((_, stepIndex) => stepIndex !== index).map((step, stepIndex) => ({ ...step, step_order: stepIndex + 1 })));
  }

  async function saveDraft() {
    setIsSaving(true);
    setActionError("");
    try {
      const saved = await updateTicketPlan(
        ticketId,
        {
          change_reason: summary,
          proposed_steps: normalizeSteps(steps),
          rollback_sql: rollbackSql.trim() ? rollbackSql : null,
          rollback_note: rollbackSql.trim() ? null : "Rollback is not applicable for this edited plan.",
          human_notes: humanNotes,
          pre_execution_notes: [
            { label: "Run during low-traffic window", enabled: true },
            { label: "Notify on-call DBA", enabled: true },
            { label: "Capture before/after metrics", enabled: true },
          ],
        },
        session.access_token,
      );
      setTicket(saved);
      onSaved(ticketId);
    } catch (saveError) {
      setActionError(saveError instanceof Error ? saveError.message : "Failed to save draft.");
    } finally {
      setIsSaving(false);
    }
  }

  async function submitDecision(decision: "approved" | "rejected") {
    if (!runId) return;
    setIsSaving(true);
    setActionError("");
    try {
      await approveRun(runId, { decision, feedback: feedback || null }, session.access_token);
      const refreshed = await getTicketDetail(ticketId, session.access_token);
      setTicket(refreshed);
    } catch (submitError) {
      setActionError(submitError instanceof Error ? submitError.message : "Failed to submit decision.");
    } finally {
      setIsSaving(false);
    }
  }

  if (error) {
    return <div className="px-5 pb-8 sm:px-8"><div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div></div>;
  }

  if (isLoading || !ticket) {
    return <div className="px-5 pb-8 sm:px-8"><div className="h-96 rounded-lg border border-slate-200 bg-white shadow-sm" /></div>;
  }

  return (
    <div className="grid gap-6 px-5 pb-8 sm:px-8 xl:grid-cols-[1fr_420px]">
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex gap-6 text-sm font-semibold text-slate-500">
            <span className="text-indigo-600">Plan Details</span>
            <span>Execution Steps ({steps.length})</span>
            <span>Rollback Plan</span>
            <span>Validation</span>
          </div>
          {mode === "detail" ? (
            <button type="button" onClick={onEdit} className="inline-flex h-9 items-center gap-2 rounded-md border border-indigo-500 px-3 text-sm font-semibold text-indigo-600 hover:bg-indigo-50">
              <Edit3 size={16} /> Edit Plan
            </button>
          ) : null}
        </div>

        <div className="space-y-5 p-5">
          <section>
            <h2 className="text-lg font-semibold text-slate-950">Plan Summary</h2>
            {mode === "edit" ? (
              <textarea
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                className="mt-3 min-h-24 w-full rounded-md border border-slate-300 p-3 text-sm leading-6 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
              />
            ) : (
              <p className="mt-3 text-sm leading-6 text-slate-700">{ticket.change_reason}</p>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold text-slate-950">Execution Steps</h2>
            {steps.map((step, index) => (
              <div key={index} className="grid gap-4 rounded-lg border border-slate-200 p-4 md:grid-cols-[240px_1fr_auto]">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="grid h-9 w-9 place-items-center rounded-md border border-slate-200 bg-slate-50 font-semibold text-indigo-600">{index + 1}</span>
                    {mode === "edit" ? (
                      <input
                        value={step.title ?? ""}
                        onChange={(event) => updateStep(index, { title: event.target.value })}
                        className="h-9 min-w-0 flex-1 rounded-md border border-slate-300 px-3 text-sm font-semibold outline-none focus:border-indigo-500"
                      />
                    ) : (
                      <span className="font-semibold text-slate-950">{step.title ?? `Step ${index + 1}`}</span>
                    )}
                  </div>
                  {mode === "edit" ? (
                    <textarea
                      value={step.description ?? ""}
                      onChange={(event) => updateStep(index, { description: event.target.value })}
                      className="mt-3 min-h-20 w-full rounded-md border border-slate-300 p-3 text-sm outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <p className="mt-3 text-sm leading-6 text-slate-600">{step.description ?? "Review SQL before execution."}</p>
                  )}
                </div>
                {mode === "edit" ? (
                  <textarea
                    value={step.action_sql}
                    onChange={(event) => updateStep(index, { action_sql: event.target.value })}
                    className="min-h-28 rounded-md border border-slate-300 p-3 font-mono text-xs leading-6 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                  />
                ) : (
                  <CodeBlock value={step.action_sql} />
                )}
                {mode === "edit" ? (
                  <button type="button" onClick={() => removeStep(index)} className="grid h-9 w-9 place-items-center rounded-md border border-red-200 text-red-600 hover:bg-red-50" aria-label="Remove step">
                    <Trash2 size={16} />
                  </button>
                ) : null}
              </div>
            ))}
            {mode === "edit" ? (
              <button type="button" onClick={addStep} className="inline-flex h-10 items-center gap-2 rounded-md border border-indigo-500 px-4 text-sm font-semibold text-indigo-600 hover:bg-indigo-50">
                <Plus size={16} /> Add Step
              </button>
            ) : null}
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-950">Validation Evidence</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {ticket.hypotheses.length ? ticket.hypotheses.map((hypothesis) => (
                <div key={hypothesis.hypothesis_id} className="rounded-lg border border-slate-200 p-4">
                  <CheckCircle2 className={hypothesis.status === "verified" ? "text-emerald-600" : "text-slate-400"} size={22} />
                  <p className="mt-3 text-sm font-semibold text-slate-950">{hypothesis.root_cause}</p>
                  <p className="mt-2 text-xs font-semibold text-emerald-700">{titleCase(hypothesis.status)}</p>
                </div>
              )) : <p className="text-sm text-slate-500">No persisted hypotheses yet.</p>}
            </div>
          </section>
        </div>
      </section>

      <aside className="space-y-5">
        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">Ticket Context</h2>
          <dl className="mt-4 grid gap-3 text-sm">
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Ticket</dt><dd className="font-semibold">{shortId(ticket.ticket_id)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Run</dt><dd className="font-semibold">{shortId(runId)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Alert</dt><dd className="font-semibold">{ticket.alert.alertname}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Instance</dt><dd className="font-semibold">{ticket.alert.instance ?? "-"}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Created</dt><dd className="font-semibold">{formatDateTime(ticket.created_at)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Updated</dt><dd className="font-semibold">{formatRelative(ticket.updated_at)}</dd></div>
          </dl>
          {runId ? (
            <button
              type="button"
              onClick={() => onOpenRun(runId)}
              className="mt-4 h-10 w-full rounded-md border border-indigo-500 text-sm font-semibold text-indigo-600 hover:bg-indigo-50"
            >
              Open Run
            </button>
          ) : null}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">Rollback Plan</h2>
          {mode === "edit" ? (
            <textarea
              value={rollbackSql}
              onChange={(event) => setRollbackSql(event.target.value)}
              className="mt-3 min-h-40 w-full rounded-md border border-slate-300 p-3 font-mono text-xs leading-6 outline-none focus:border-indigo-500"
            />
          ) : (
            <div className="mt-3"><CodeBlock value={rollbackLines} /></div>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">{mode === "edit" ? "Human Notes" : "Human Feedback"}</h2>
          <textarea
            value={mode === "edit" ? humanNotes : feedback}
            onChange={(event) => mode === "edit" ? setHumanNotes(event.target.value) : setFeedback(event.target.value)}
            placeholder="Enter review comments, concerns, or approval notes..."
            className="mt-3 min-h-36 w-full rounded-md border border-slate-300 p-3 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
          />
          {actionError ? <p className="mt-2 text-sm text-red-600">{actionError}</p> : null}
          {mode === "edit" ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button type="button" onClick={() => onSaved(ticketId)} className="h-11 rounded-md border border-slate-300 font-semibold text-slate-700 hover:bg-slate-50">Cancel</button>
              <button type="button" disabled={isSaving} onClick={saveDraft} className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-indigo-600 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
                <Save size={17} /> Save Draft
              </button>
            </div>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                disabled={!canApprove || isSaving || !feedback.trim()}
                onClick={() => submitDecision("rejected")}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-red-500 font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <XCircle size={18} /> Reject
              </button>
              <button
                type="button"
                disabled={!canApprove || isSaving}
                onClick={() => submitDecision("approved")}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-emerald-600 font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <CheckCircle2 size={18} /> Approve & Execute
              </button>
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}
