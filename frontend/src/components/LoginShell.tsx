import type { ReactNode } from "react";

type LoginShellProps = {
  children: ReactNode;
};

export function LoginShell({ children }: LoginShellProps) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-50 px-5 py-10">
      <div className="absolute left-8 top-8 grid grid-cols-5 gap-4 opacity-20">
        {Array.from({ length: 35 }).map((_, index) => (
          <span key={index} className="h-1 w-1 rounded-full bg-slate-400" />
        ))}
      </div>
      <div className="absolute bottom-8 right-8 grid grid-cols-5 gap-4 opacity-20">
        {Array.from({ length: 30 }).map((_, index) => (
          <span key={index} className="h-1 w-1 rounded-full bg-slate-400" />
        ))}
      </div>
      <div className="absolute -left-28 bottom-[-7rem] h-80 w-80 rounded-full border border-slate-200" />
      <div className="absolute -right-28 top-[-7rem] h-80 w-80 rounded-full border border-slate-200" />
      <section className="relative w-full max-w-[445px] rounded-lg border border-slate-200 bg-white/95 p-8 shadow-login-card backdrop-blur sm:p-10">
        {children}
      </section>
    </main>
  );
}
