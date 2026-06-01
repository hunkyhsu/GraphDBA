import { useState, type FormEvent } from "react";
import { Eye, EyeOff, LockKeyhole, UserRound } from "lucide-react";

import { BrandMark } from "../../components/BrandMark";
import { LoginShell } from "../../components/LoginShell";
import { TextInput } from "../../components/TextInput";
import { login, type LoginResponse } from "../../lib/api";
import { saveSession } from "../../lib/authStorage";

type LoginPageProps = {
  onAuthenticated: (session: LoginResponse) => void;
};

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const loginResponse = await login({
        employee_id: employeeId.trim(),
        password,
      });
      saveSession(loginResponse, remember);
      onAuthenticated(loginResponse);
      setPassword("");
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <LoginShell>
      <div className="flex flex-col items-center text-center">
        <BrandMark />
        <h1 className="mt-3 text-3xl font-bold tracking-normal text-slate-950">
          GraphDBA
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Database Autonomous Operations
        </p>
      </div>

      <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          <label className="block text-left">
            <span className="text-sm font-semibold text-slate-800">
              Employee ID
            </span>
            <TextInput
              icon={<UserRound size={18} strokeWidth={1.8} />}
              value={employeeId}
              onChange={(event) => setEmployeeId(event.target.value)}
              placeholder="Enter your employee ID"
              autoComplete="username"
              required
              className="mt-2"
            />
          </label>

          <label className="block text-left">
            <span className="text-sm font-semibold text-slate-800">
              Password
            </span>
            <TextInput
              icon={<LockKeyhole size={18} strokeWidth={1.8} />}
              rightAdornment={
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="rounded p-1 text-slate-600 hover:bg-slate-100"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff size={18} strokeWidth={1.8} />
                  ) : (
                    <Eye size={18} strokeWidth={1.8} />
                  )}
                </button>
              }
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              className="mt-2"
            />
          </label>

          <div className="flex items-center justify-between gap-4 text-sm">
            <label className="flex items-center gap-2 font-medium text-slate-700">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 accent-indigo-600 focus:ring-indigo-500"
              />
              Remember me
            </label>
            <button
              type="button"
              className="font-semibold text-indigo-600 hover:text-indigo-700"
            >
              Forgot password?
            </button>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="h-11 w-full rounded-md bg-indigo-600 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-4 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-indigo-400"
          >
            {isSubmitting ? "Signing in..." : "Log In"}
          </button>
      </form>

      <div className="mt-7 border-t border-slate-200 pt-5 text-center text-xs text-slate-400">
        © 2026 GraphDBA. All rights reserved.
      </div>
    </LoginShell>
  );
}
