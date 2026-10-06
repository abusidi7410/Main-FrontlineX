export interface PrintOptions {
  title: string;
  bodyHtml: string;
  styles?: string;
}

export interface PrintSchoolProfile {
  name: string;
  address?: string | undefined;
  phone?: string | undefined;
  email?: string | undefined;
  logoUrl?: string | null | undefined;
}

/** Escape text before it goes into a printable document's markup. */
export function escapeHtml(value: string | null | undefined): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/**
 * The letterhead every printable document opens with. School information always
 * comes from the school's own saved profile — never a hardcoded string — so a
 * receipt or registration document carries whatever the school last saved in
 * Settings, including its logo.
 */
export function schoolHeading(school: PrintSchoolProfile): string {
  const logo = school.logoUrl
    ? `<img src="${escapeHtml(school.logoUrl)}" alt="" style="height:46px;display:block;margin-bottom:8px" />`
    : "";
  const contact = [school.phone, school.email].filter(Boolean).join(" · ");
  const lines = [school.name, school.address, contact].filter(Boolean);
  return `<div class="letterhead">${logo}<div><p class="school-name">${escapeHtml(school.name)}</p><p class="school-meta">${lines.slice(1).map(escapeHtml).join(" &middot; ")}</p></div></div>`;
}

export function documentMarkup(options: PrintOptions): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(options.title)}</title>
<style>
  body { font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #0f172a; line-height: 1.5; margin: 40px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .letterhead { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 20px; }
  .school-name { font-size: 18px; font-weight: 700; color: #0f172a; margin: 0; }
  .school-meta { font-size: 12px; color: #475569; margin: 2px 0 0; }
  .doc { border: 1px solid #e2e8f0; padding: 24px; margin: 16px 0; border-radius: 10px; background: #fff; }
  h1 { font-size: 22px; margin: 0 0 4px; color: #0f172a; }
  h2 { font-size: 14px; margin: 12px 0 4px; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #e2e8f0; }
  th { color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .right { text-align: right; }
  .center { text-align: center; }
  .total { font-weight: 700; font-size: 15px; }
  .muted { color: #475569; }
  .fine { color: #64748b; font-size: 12px; margin-top: 16px; }
  .badge { display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
  .badge-paid { background: #dcfce7; color: #166534; }
  .badge-partial { background: #fef9c3; color: #854d0e; }
  .badge-unpaid { background: #fee2e2; color: #991b1b; }
  .doc-meta { color: #475569; font-size: 13px; margin-top: 2px; }
  @media print { body { margin: 0; } }
  ${options.styles ?? ""}
</style>
</head>
<body>
${options.bodyHtml}
</body>
</html>`;
}

/**
 * Print the document from a hidden same-origin iframe. This is the path that
 * matters in practice: it needs no pop-up permission, so it still works on
 * mobile browsers (and in any browser with pop-ups blocked) where
 * `window.open` simply returns null and the user is left with nothing to print.
 */
function printFromIframe(markup: string): boolean {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.setAttribute("tabindex", "-1");
  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.style.visibility = "hidden";
  document.body.appendChild(frame);

  const target = frame.contentWindow;
  if (!target || !frame.contentDocument) {
    frame.remove();
    return false;
  }
  frame.contentDocument.open();
  frame.contentDocument.write(markup);
  frame.contentDocument.close();
  target.focus();

  // Wait for the document to finish loading so the school's logo is on the
  // printed page rather than a broken image, with a deadline so a stalled
  // asset can never leave the user with no print dialog at all.
  let printed = false;
  const runPrint = () => {
    if (printed) return;
    printed = true;
    try {
      target.print();
    } finally {
      frame.remove();
    }
  };
  if (frame.contentDocument.readyState === "complete") {
    setTimeout(runPrint, 50);
  } else {
    target.addEventListener("load", () => setTimeout(runPrint, 50), { once: true });
    setTimeout(runPrint, 2000);
  }
  return true;
}

/**
 * Renders a document and starts the print dialog, keeping the user on the page
 * they were reading. Returns false only when no printing path is available.
 */
export function printHtml(options: PrintOptions): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  const markup = documentMarkup(options);
  if (printFromIframe(markup)) return true;

  // Fallback for environments that refuse an iframe (some embedded webviews):
  // a real window the user can also save or print by hand.
  const win = window.open("", "_blank", "width=820,height=960");
  if (!win) return false;
  win.document.write(markup);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 250);
  return true;
}
