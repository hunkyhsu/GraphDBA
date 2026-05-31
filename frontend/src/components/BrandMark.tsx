export function BrandMark() {
  return (
    <div className="relative h-12 w-12" aria-hidden="true">
      <div className="absolute left-1/2 top-1/2 h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full border-[7px] border-indigo-600 border-l-indigo-400 border-t-indigo-400" />
      <div className="absolute left-2 top-1.5 h-2.5 w-2.5 rounded-full bg-indigo-600" />
      <div className="absolute bottom-1.5 right-2 h-2.5 w-2.5 rounded-full bg-indigo-500" />
    </div>
  );
}
