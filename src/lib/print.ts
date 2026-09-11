export interface PrintOptions {
  title: string;
  bodyHtml: string;
  styles?: string;
}

/**
 * Opens a printable document in a new window and starts the print dialog.
 * Returns false when pop-ups are blocked so callers can tell the user.
 */
export function printHtml(options: PrintOptions): boolean {
  if (typeof window === "undefined") return false;
  const win = window.open("", "_blank", "width=820,height=960");
  if (!win) return false;
  win.document.write(`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${options.title}</title>
<style>
  body { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #0f172a; margin: 40px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .school { font-size: 13px; color: #475569; margin-bottom: 4px; }
  .doc { border: 1px solid #cbd5e1; padding: 20px; margin: 16px 0; border-radius: 8px; }
  h1 { font-size: 20px; margin: 0 0 16px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid #e2e8f0; }
  th { color: #475569; font-size: 12px; text-transform: uppercase; }
  .right { text-align: right; }
  .center { text-align: center; }
  .total { font-weight: 700; font-size: 15px; }
  .muted { color: #475569; }
  .fine { color: #475569; font-size: 12px; margin-top: 16px; }
  @media print { body { margin: 0; } }
  ${options.styles ?? ""}
</style>
</head>
<body>
${options.bodyHtml}
</body>
</html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 250);
  return true;
}
