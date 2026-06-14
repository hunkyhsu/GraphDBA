import type { ComponentPropsWithoutRef, ReactNode } from "react";

type TextInputProps = ComponentPropsWithoutRef<"input"> & {
  icon: ReactNode;
  rightAdornment?: ReactNode;
};

export function TextInput({ icon, rightAdornment, className = "", ...props }: TextInputProps) {
  return (
    <div className={`relative ${className}`}>
      <div className="pointer-events-none absolute inset-y-0 left-3.5 grid w-5 place-items-center text-slate-500">
        {icon}
      </div>
      <input
        className={[
          "h-11 w-full rounded-md border border-slate-300 bg-white pl-11 pr-11 text-sm text-slate-900 outline-none transition",
          "placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100",
        ].join(" ")}
        {...props}
      />
      {rightAdornment ? (
        <div className="absolute inset-y-0 right-3 grid w-8 place-items-center text-slate-600">
          {rightAdornment}
        </div>
      ) : null}
    </div>
  );
}
