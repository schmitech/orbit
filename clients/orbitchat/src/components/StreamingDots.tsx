export function StreamingDots({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-2 w-2' : 'h-2.5 w-2.5';
  return (
    <div className="flex items-center gap-1.5 py-1">
      {([0, 150, 300] as const).map(delay => (
        <span key={delay} className={`inline-block ${cls} animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]`} style={{ animationDelay: `${delay}ms` }} />
      ))}
    </div>
  );
}
