import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { useSession } from "@/auth/session";
import {
  printInvoiceDocument,
  printReceiptDocument,
  toPrintProfile,
  type PrintSchoolProfile,
} from "@/lib/documents";
import { getSchoolProfile } from "@/services/school.service";
import type { Invoice, Payment } from "@/types";

const MISSING_PROFILE_MESSAGE =
  "Your school profile is missing. Save your school details in Settings before printing.";

/**
 * Printing invoices and receipts from anywhere in the app.
 *
 * The letterhead comes from the school's own saved profile. The session copy is
 * used when it is there; when it is not — an older stored session, or an account
 * whose profile was saved on another device — the profile endpoint is consulted
 * once and cached, so a document is never blocked by a missing session field.
 */
export function usePrintDocuments() {
  const { session } = useSession();
  const sessionProfile = toPrintProfile(session?.school);
  const [resolving, setResolving] = useState(false);
  const profile = useQuery({
    queryKey: ["school-profile"],
    queryFn: getSchoolProfile,
    enabled: sessionProfile === null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const resolveProfile = useCallback(async (): Promise<PrintSchoolProfile | null> => {
    if (sessionProfile) return sessionProfile;
    try {
      const fromQuery = profile.data ?? (await profile.refetch()).data;
      return toPrintProfile(fromQuery);
    } catch {
      return null;
    }
  }, [profile, sessionProfile]);

  const withProfile = useCallback(
    async (print: (school: PrintSchoolProfile) => boolean) => {
      setResolving(true);
      try {
        const school = await resolveProfile();
        if (!school) {
          toast.error(MISSING_PROFILE_MESSAGE);
          return;
        }
        if (!print(school)) {
          toast.error(
            "We couldn't open the print dialog. Check that printing is allowed for this site.",
          );
        }
      } finally {
        setResolving(false);
      }
    },
    [resolveProfile],
  );

  const printInvoice = useCallback(
    (invoice: Invoice) => withProfile((school) => printInvoiceDocument(invoice, school)),
    [withProfile],
  );

  const printReceipt = useCallback(
    (payment: Payment) => withProfile((school) => printReceiptDocument(payment, school)),
    [withProfile],
  );

  return { printInvoice, printReceipt, resolveProfile: resolveProfile, resolving };
}
