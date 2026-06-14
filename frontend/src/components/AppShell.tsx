import type { ReactNode } from "react";
import {
  Bell,
  Bot,
  BriefcaseBusiness,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  PlayCircle,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { BrandMark } from "./BrandMark";
import type { LoginResponse } from "../lib/api";

export type AppView = "dashboard" | "alerts" | "agent" | "tickets" | "runs";

type AppShellProps = {
  session: LoginResponse;
  active: AppView;
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  onNavigate: (view: AppView) => void;
  onSignOut: () => void;
  children: ReactNode;
};

const navItems: Array<{ key: AppView; label: string; icon: LucideIcon }> = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "alerts", label: "Alerts", icon: TriangleAlert },
  { key: "agent", label: "Agent", icon: Bot },
  { key: "tickets", label: "Tickets", icon: BriefcaseBusiness },
  { key: "runs", label: "Runs", icon: PlayCircle },
];

export function AppShell({
  session,
  active,
  title,
  subtitle,
  actions,
  onNavigate,
  onSignOut,
  children,
}: AppShellProps) {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 bg-slate-950 text-white lg:flex lg:flex-col">
          <div className="flex h-24 items-center gap-3 px-7">
            <BrandMark />
            <span className="text-2xl font-semibold">GraphDBA</span>
          </div>
          <nav className="flex-1 space-y-2 px-4">
            {navItems.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => onNavigate(key)}
                className={`flex h-14 w-full items-center gap-4 rounded-lg px-5 text-left text-base font-medium transition ${
                  active === key
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-950/30"
                    : "text-slate-300 hover:bg-white/10"
                }`}
              >
                <Icon size={22} />
                {label}
              </button>
            ))}
          </nav>
          <div className="px-7 pb-8">
            <div className="relative h-44 overflow-hidden rounded-lg border border-indigo-400/20 bg-slate-900">
              <div className="absolute left-1/2 top-10 h-16 w-24 -translate-x-1/2 rotate-45 border border-indigo-400/35 bg-indigo-500/10" />
              <div className="absolute left-1/2 top-16 h-16 w-24 -translate-x-1/2 rotate-45 border border-indigo-400/30 bg-indigo-500/20" />
              <div className="absolute left-1/2 top-[5.5rem] h-16 w-24 -translate-x-1/2 rotate-45 border border-indigo-400/25 bg-indigo-500/15" />
            </div>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <header className="flex min-h-20 items-center justify-between gap-4 px-5 py-4 sm:px-8">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <div className="lg:hidden">
                  <BrandMark />
                </div>
                {title ? (
                  <h1 className="truncate text-3xl font-semibold tracking-normal text-slate-950">{title}</h1>
                ) : null}
              </div>
              {subtitle ? <div className="mt-2 text-sm text-slate-500">{subtitle}</div> : null}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {actions}
              <button
                type="button"
                className="grid h-10 w-10 place-items-center rounded-md text-slate-600 hover:bg-white hover:text-slate-950"
                aria-label="Notifications"
              >
                <Bell size={20} />
              </button>
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-full bg-indigo-600 text-sm font-semibold text-white">
                  {session.user.name.charAt(0).toUpperCase()}
                </div>
                <p className="hidden text-sm font-semibold text-slate-950 sm:block">{session.user.name}</p>
                <ChevronDown className="hidden text-slate-500 sm:block" size={16} />
                <button
                  type="button"
                  onClick={onSignOut}
                  className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-white hover:text-slate-950"
                  aria-label="Sign out"
                >
                  <LogOut size={18} />
                </button>
              </div>
            </div>
          </header>
          {children}
        </section>
      </div>
    </main>
  );
}
