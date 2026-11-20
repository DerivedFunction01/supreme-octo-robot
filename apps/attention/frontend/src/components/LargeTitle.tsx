// The in-view large title + subtitle the section views open
// with (storyboard metrics in app.css). Presentation only —
// the shell's chrome is the kit's AppShell.
export function LargeTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <>
      <h2 className="largetitle at-largetitle">{title}</h2>
      <p className="subtitle">{subtitle}</p>
    </>
  );
}
