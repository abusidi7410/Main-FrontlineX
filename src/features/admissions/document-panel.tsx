import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Paperclip, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError, downloadBlob } from "@/api/client";
import { dateTimeFmt } from "@/lib/format";
import {
  deleteAdmissionDocument,
  downloadAdmissionDocument,
  reviewAdmissionDocument,
  uploadAdmissionDocument,
} from "@/services/admissions.service";
import {
  ADMISSION_DOCUMENT_CATEGORIES,
  ADMISSION_DOCUMENT_LABELS,
  type AdmissionDocument,
  type AdmissionDocumentCategory,
} from "@/types";

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    const fieldErrors = error.fieldErrors;
    const first = fieldErrors ? Object.values(fieldErrors)[0] : undefined;
    return first ?? error.message;
  }
  return fallback;
}

export function DocumentPanel({
  applicationId,
  documents,
  requiredDocuments,
  editable,
  canWrite,
  canReview,
}: {
  applicationId: string;
  documents: AdmissionDocument[];
  requiredDocuments: AdmissionDocumentCategory[];
  /** Draft applications may have documents added or removed. */
  editable: boolean;
  canWrite: boolean;
  canReview: boolean;
}) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [category, setCategory] = useState<AdmissionDocumentCategory>("birth_certificate");
  const [rejecting, setRejecting] = useState<AdmissionDocument | null>(null);
  const [rejectNote, setRejectNote] = useState("");

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admission", applicationId] });
    await queryClient.invalidateQueries({ queryKey: ["admissions"] });
  };

  const upload = useMutation({
    mutationFn: (file: File) => uploadAdmissionDocument(applicationId, { category, file }),
    onSuccess: async (document) => {
      toast.success(`${document.categoryLabel} uploaded.`);
      if (fileInput.current) fileInput.current.value = "";
      await invalidate();
    },
    onError: (error) => {
      toast.error(errorMessage(error, "That file could not be uploaded."));
    },
  });

  const remove = useMutation({
    mutationFn: deleteAdmissionDocument,
    onSuccess: async () => {
      toast.success("Document removed.");
      await invalidate();
    },
    onError: (error) => {
      toast.error(errorMessage(error, "That document could not be removed."));
    },
  });

  const review = useMutation({
    mutationFn: (input: {
      document: AdmissionDocument;
      status: "verified" | "rejected";
      note?: string;
    }) => reviewAdmissionDocument(input.document.id, { status: input.status, note: input.note }),
    onSuccess: async (document) => {
      toast.success(`${document.categoryLabel} marked ${document.status}.`);
      setRejecting(null);
      setRejectNote("");
      await invalidate();
    },
    onError: (error) => {
      toast.error(errorMessage(error, "That review could not be saved."));
    },
  });

  const download = useMutation({
    mutationFn: (document: AdmissionDocument) =>
      downloadAdmissionDocument(document.id).then((blob) => ({ blob, document })),
    onSuccess: ({ blob, document }) => downloadBlob(blob, document.originalFilename),
    onError: (error) => {
      toast.error(errorMessage(error, "That document could not be downloaded."));
    },
  });

  const verifiedCategories = new Set(
    documents.filter((d) => d.status === "verified").map((d) => d.category),
  );

  return (
    <div className="space-y-4">
      {requiredDocuments.length > 0 ? (
        <ul className="flex flex-wrap gap-2" aria-label="Required documents">
          {requiredDocuments.map((required) => {
            const done = verifiedCategories.has(required);
            return (
              <li
                key={required}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
                  done
                    ? "border-success/25 bg-success-soft text-success"
                    : "border-warning/25 bg-warning-soft text-warning"
                }`}
              >
                {done ? (
                  <Check className="size-3.5" aria-hidden="true" />
                ) : (
                  <X className="size-3.5" aria-hidden="true" />
                )}
                {ADMISSION_DOCUMENT_LABELS[required]}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          This school does not require any documents before approval.
        </p>
      )}

      {canWrite && editable ? (
        <div className="fn-panel flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="documentCategory">Document type</Label>
            <Select
              value={category}
              onValueChange={(value) => setCategory(value as AdmissionDocumentCategory)}
            >
              <SelectTrigger id="documentCategory" className="h-12">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADMISSION_DOCUMENT_CATEGORIES.map((option) => (
                  <SelectItem key={option} value={option}>
                    {ADMISSION_DOCUMENT_LABELS[option]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="documentFile">File (PDF or image, up to 10 MB)</Label>
            <input
              ref={fileInput}
              id="documentFile"
              type="file"
              accept="application/pdf,image/jpeg,image/png,image/webp"
              className="block h-12 w-full rounded-xl border border-input bg-background px-3 text-sm file:mr-3 file:h-8 file:rounded-lg file:border-0 file:bg-muted file:px-3 file:text-sm"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
              }}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            className="h-12"
            disabled={upload.isPending}
            onClick={() => fileInput.current?.click()}
          >
            <Upload className="size-4" aria-hidden="true" />
            {upload.isPending ? "Uploading…" : "Choose file"}
          </Button>
        </div>
      ) : null}

      {documents.length === 0 ? (
        <p className="flex items-center gap-2 rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          <Paperclip className="size-4" aria-hidden="true" />
          No documents attached yet.
        </p>
      ) : (
        <ul className="fn-panel divide-y">
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{document.categoryLabel}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {document.originalFilename} · {formatBytes(document.sizeBytes)} ·{" "}
                  {dateTimeFmt(document.uploadedAt)}
                  {document.uploadedBy ? ` · by ${document.uploadedBy}` : ""}
                </p>
                {document.reviewNote ? (
                  <p className="text-sm text-muted-foreground">Note: {document.reviewNote}</p>
                ) : null}
              </div>
              <StatusBadge status={document.status} />
              <Button
                variant="ghost"
                className="h-11"
                disabled={download.isPending}
                onClick={() => download.mutate(document)}
              >
                <Download className="size-4" aria-hidden="true" />
                View
              </Button>
              {canReview && document.status === "pending" ? (
                <>
                  <Button
                    variant="outline"
                    className="h-11"
                    disabled={review.isPending}
                    onClick={() => review.mutate({ document, status: "verified" })}
                  >
                    Verify
                  </Button>
                  <Button
                    variant="ghost"
                    className="h-11 text-destructive"
                    onClick={() => {
                      setRejecting(document);
                      setRejectNote("");
                    }}
                  >
                    Reject
                  </Button>
                </>
              ) : null}
              {canWrite && editable ? (
                <Button
                  variant="ghost"
                  className="h-11 text-destructive"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(document.id)}
                  aria-label={`Remove ${document.categoryLabel}`}
                >
                  <Trash2 className="size-4" aria-hidden="true" />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <Dialog open={rejecting !== null} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this document?</DialogTitle>
            <DialogDescription>
              Give the family a reason so they can bring a corrected copy.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="rejectNote">Reason</Label>
            <Textarea
              id="rejectNote"
              rows={3}
              value={rejectNote}
              onChange={(event) => setRejectNote(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={review.isPending || rejectNote.trim() === ""}
              onClick={() => {
                if (rejecting) {
                  review.mutate({ document: rejecting, status: "rejected", note: rejectNote });
                }
              }}
            >
              Reject document
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
