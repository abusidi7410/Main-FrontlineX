import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Pin, PinOff, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuthenticatedSession } from "@/auth/session";
import { dateFmt, dateTimeFmt } from "@/lib/format";
import {
  AUDIENCE_OPTIONS,
  audiencePreview,
  defaultAudience,
  orderBoard,
  selectAudience,
  toIsoMinute,
  type AudienceOption,
} from "@/features/announcements/announcement-model";
import {
  createAnnouncement,
  deleteAnnouncement,
  getAnnouncements,
  updateAnnouncement,
} from "@/services/school.service";

export const Route = createFileRoute("/_app/communication")({
  head: () => ({
    meta: [
      { title: "Announcements — Frontline Nexus" },
      {
        name: "description",
        content:
          "Send announcements to staff, parents and students, and see everything already published.",
      },
      { property: "og:title", content: "Announcements — Frontline Nexus" },
      { property: "og:description", content: "Send announcements to staff, parents and students." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: CommunicationPage,
});

function CommunicationPage() {
  const { can, user } = useAuthenticatedSession();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["announcements"], queryFn: getAnnouncements });
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  // A parent or student composing here almost always means "our side", so the
  // audience starts on their own group rather than the whole school. Publishing
  // "All" has to be a deliberate second click, not a default.
  const [audience, setAudience] = useState<string[]>(() => defaultAudience(user.role));
  const [expiresAt, setExpiresAt] = useState("");
  // The composer starts collapsed so parents and students, who only ever read
  // this page, are not shown a form they cannot use.
  const [composing, setComposing] = useState(false);

  const canWrite = can("communication.write");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["announcements"] });

  const create = useMutation({
    mutationFn: () =>
      createAnnouncement({
        title: title.trim(),
        body: body.trim(),
        audience,
        isPinned: false,
        expiresAt: toIsoMinute(expiresAt),
      }),
    onSuccess: async () => {
      toast.success("Announcement published.");
      setTitle("");
      setBody("");
      setAudience(defaultAudience(user.role));
      setExpiresAt("");
      setComposing(false);
      await refresh();
    },
    onError: () => toast.error("We couldn't publish that announcement. Please try again."),
  });

  const togglePin = useMutation({
    mutationFn: ({ id, isPinned }: { id: string; isPinned: boolean }) =>
      updateAnnouncement(id, { isPinned }),
    onSuccess: async (_data, variables) => {
      toast.success(variables.isPinned ? "Announcement pinned." : "Announcement unpinned.");
      await refresh();
    },
    onError: () => toast.error("We couldn't update that announcement."),
  });

  const remove = useMutation({
    mutationFn: deleteAnnouncement,
    onSuccess: async () => {
      toast.success("Announcement deleted.");
      await refresh();
    },
    onError: () => toast.error("We couldn't delete that announcement."),
  });

  // Pinned first, then newest. The backend already sorts this way; ordering
  // again here keeps the board correct if the response is ever cached or merged
  // from more than one source.
  const board = orderBoard(query.data ?? []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Announcements"
        description="One message, delivered in-app to exactly the people who need it."
        actions={
          canWrite ? (
            <Button onClick={() => setComposing((v) => !v)}>
              {composing ? "Close composer" : "New announcement"}
            </Button>
          ) : undefined
        }
      />

      {canWrite && composing ? (
        <form
          className="fn-panel space-y-4 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (title.trim() && body.trim()) create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              className="h-12"
              value={title}
              maxLength={180}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="body">Message</Label>
            <Textarea
              id="body"
              rows={4}
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Audience</legend>
            <div className="flex flex-wrap gap-2">
              {AUDIENCE_OPTIONS.map((option) => {
                const on = audience.includes(option);
                return (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setAudience((prev) => selectAudience(prev, option as AudienceOption))}
                    className={
                      on
                        ? "min-h-11 rounded-full border border-primary bg-primary-soft px-4 font-medium text-primary"
                        : "min-h-11 rounded-full border bg-surface px-4 font-medium hover:bg-muted"
                    }
                  >
                    {option}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              This reaches {audiencePreview(audience)}.
            </p>
          </fieldset>
          <div className="space-y-1.5">
            <Label htmlFor="expires">Expires on (optional)</Label>
            <Input
              id="expires"
              type="datetime-local"
              className="h-12"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
            <p className="text-sm text-muted-foreground">
              After this moment the notice leaves the board on its own. Leave it blank to keep it
              until you delete it.
            </p>
          </div>
          <Button
            type="submit"
            className="h-12 text-base sm:w-auto"
            disabled={create.isPending || !title.trim() || !body.trim()}
          >
            {create.isPending ? "Publishing…" : "Publish announcement"}
          </Button>
        </form>
      ) : null}

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : board.length === 0 ? (
        <EmptyState
          title="Nothing published yet"
          description={
            canWrite
              ? "Publish your first announcement and it will appear in every recipient's notifications."
              : "When the school publishes a notice to you, it will appear here."
          }
        />
      ) : (
        <ul className="fn-panel divide-y">
          {board.map((item) => (
            <li key={item.id} className={item.isPinned ? "bg-primary-soft/40" : undefined}>
              <div className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold">
                      {item.title}
                      {item.isPinned ? (
                        <span className="ml-2 align-middle text-xs font-medium text-primary">
                          Pinned
                        </span>
                      ) : null}
                      {item.scope === "platform" ? (
                        <span className="ml-2 align-middle text-xs font-medium text-muted-foreground">
                          From Frontline Nexus
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-1 whitespace-pre-line text-muted-foreground">{item.body}</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {item.author} · {dateTimeFmt(item.createdAt)} · {item.audience.join(", ")}
                      {item.expiresAt ? ` · expires ${dateFmt(item.expiresAt)}` : ""}
                    </p>
                  </div>
                  {canWrite && item.scope === "school" ? (
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => togglePin.mutate({ id: item.id, isPinned: !item.isPinned })}
                        disabled={togglePin.isPending}
                      >
                        {item.isPinned ? (
                          <PinOff className="size-4" aria-hidden="true" />
                        ) : (
                          <Pin className="size-4" aria-hidden="true" />
                        )}
                        {item.isPinned ? "Unpin" : "Pin"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          if (remove.isPending) return;
                          if (
                            window.confirm(
                              `Delete "${item.title}"? Everyone who received it will lose it from their notifications.`,
                            )
                          ) {
                            remove.mutate(item.id);
                          }
                        }}
                        disabled={remove.isPending}
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                        Delete
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
