import { useEffect, useState } from "react";
import { ArrowRight, Search } from "lucide-react";

import { listTickets, type LoginResponse, type TicketListItem } from "../../lib/api";
import { formatRelative, shortId, titleCase } from "../../lib/format";

type TicketsPageProps = {
  session: LoginResponse;
  onOpenTicket: (ticketId: string) => void;
};

export function TicketsPage({ session, onOpenTicket }: TicketsPageProps) {
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    listTickets(session.access_token)
      .then((response) => {
        if (isActive) setTickets(response.items);
      })
      .catch((loadError) => {
        if (isActive) setError(loadError instanceof Error ? loadError.message : "Failed to load tickets.");
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });
    return () => {
      isActive = false;
    };
  }, [session.access_token]);

  return (
    <div className="space-y-5 px-5 pb-8 sm:px-8">
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <label className="relative block max-w-lg">
          <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input
            placeholder="Search ticket, alert, instance, or plan..."
            className="h-11 w-full rounded-md border border-slate-300 bg-white pl-11 pr-4 text-sm text-slate-900 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
          />
        </label>
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="grid min-w-[760px] grid-cols-[1.2fr_1fr_120px_120px_120px_60px] gap-4 border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-semibold text-slate-500">
          <span>Ticket</span>
          <span>Run</span>
          <span>Status</span>
          <span>Risk</span>
          <span>Updated</span>
          <span />
        </div>
        <div className="overflow-x-auto">
          {error ? (
            <div className="p-5 text-sm text-red-600">{error}</div>
          ) : isLoading ? (
            <div className="h-48 bg-slate-50" />
          ) : tickets.length ? tickets.map((ticket) => (
            <button
              key={ticket.ticket_id}
              type="button"
              onClick={() => onOpenTicket(ticket.ticket_id)}
              className="grid min-w-[760px] grid-cols-[1.2fr_1fr_120px_120px_120px_60px] gap-4 border-b border-slate-100 px-5 py-4 text-left hover:bg-slate-50"
            >
              <span>
                <span className="block font-semibold text-slate-950">{ticket.alertname}</span>
                <span className="mt-1 block text-sm text-slate-500">{shortId(ticket.ticket_id)}</span>
              </span>
              <span className="self-center text-sm text-slate-600">{shortId(ticket.run_id)}</span>
              <span className="self-center text-sm font-semibold text-amber-700">{titleCase(ticket.status)}</span>
              <span className="self-center text-sm text-slate-600">{titleCase(ticket.risk_level)}</span>
              <span className="self-center text-sm text-slate-500">{formatRelative(ticket.updated_at)}</span>
              <span className="self-center text-indigo-600"><ArrowRight size={18} /></span>
            </button>
          )) : (
            <div className="p-8 text-sm text-slate-500">No tickets found.</div>
          )}
        </div>
      </section>
    </div>
  );
}
