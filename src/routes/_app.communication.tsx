import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/auth/session";
import { dateTimeFmt } from "@/lib/format";
import { createAnnouncement, getAnnouncements } from "@/services/school.service";

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

const AUDIENCES = ["All", "Staff", "Parents", "Students"];

function CommunicationPage() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["announcements"], queryFn: getAnnouncements });
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState<string[]>(["All"]);

  const create = useMutation({
    mutationFn: () => createAnnouncement({ title, body, audience }),
    onSuccess: async () => {
      toast.success("Announcement published.");
      setTitle("");
      setBody("");
      await queryClient.invalidateQueries({ queryKey: ["announcements"] });
    },
    onError: () => toast.error("We couldn't publish that announcement. Please try again."),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Announcements"
        description="One message, delivered in-app to exactly the people who need it."
      />

      {can("communication.write") ? (
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
              {AUDIENCES.map((option) => {
                const on = audience.includes(option);
                return (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      setAudience((prev) =>
                        prev.includes(option)
                          ? prev.filter((a) => a !== option)
                          : [...prev, option],
                      )
                    }
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
          </fieldset>
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
      ) : (
        <ul className="fn-panel divide-y">
          {query.data.map((item) => (
            <li key={item.id} className="p-5">
              <p className="font-semibold">{item.title}</p>
              <p className="mt-1 text-muted-foreground">{item.body}</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {item.author} · {dateTimeFmt(item.createdAt)} · {item.audience.join(", ")}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
