export function Panel({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-surface-border-subtle bg-surface-card ${className}`}>
      {title && (
        <header className="border-b border-surface-border-subtle px-5 py-3">
          <h2 className="text-sm font-medium text-text">{title}</h2>
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
