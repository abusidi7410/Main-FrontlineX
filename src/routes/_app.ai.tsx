import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuthenticatedSession } from "@/auth/session";
import { numberFmt } from "@/lib/format";
import { AI_TOOLS, askAi, type AiMessage } from "@/services/ai.service";
import { getSubscription } from "@/services/school.service";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/ai")({
  head: () => ({
    meta: [
      { title: "AI assistant — Frontline Nexus" },
      {
        name: "description",
        content:
          "A role-aware AI assistant that only sees the data your role is allowed to access.",
      },
      { property: "og:title", content: "AI assistant — Frontline Nexus" },
      {
        property: "og:description",
        content: "A role-aware AI assistant, scoped to your permissions.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AiPage,
});

function AiPage() {
  const { user, can } = useAuthenticatedSession();
  const subscription = useQuery({ queryKey: ["subscription"], queryFn: getSubscription });
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<AiMessage[]>([]);

  const tools = AI_TOOLS.filter((tool) => can(tool.permission));

  const ask = useMutation({
    mutationFn: (text: string) =>
      askAi({ prompt: text, role: user.role, permissions: user.permissions }),
    onSuccess: (message) => setMessages((prev) => [...prev, message]),
  });

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { id: `u_${Date.now()}`, role: "user", content: trimmed }]);
    setPrompt("");
    ask.mutate(trimmed);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI assistant"
        description="Ask about your school in plain language. The assistant can only use data your role is permitted to see."
      />

      {subscription.data ? (
        <p className="text-sm text-muted-foreground">
          AI credits used this month: {numberFmt(subscription.data.aiCreditsUsed)} of{" "}
          {numberFmt(subscription.data.aiCreditsTotal)}
        </p>
      ) : null}

      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {tools.map((tool) => (
          <li key={tool.id}>
            <button
              type="button"
              onClick={() => send(tool.prompt)}
              className="fn-panel h-full w-full p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary-soft/40"
            >
              <Sparkles className="size-5 text-primary" aria-hidden="true" />
              <p className="mt-2 font-medium">{tool.label}</p>
              <p className="text-sm text-muted-foreground">{tool.description}</p>
            </button>
          </li>
        ))}
      </ul>

      <section className="fn-panel p-5" aria-label="Conversation" aria-live="polite">
        {messages.length === 0 ? (
          <p className="text-muted-foreground">
            Start with one of the suggestions above, or type your own question below.
          </p>
        ) : (
          <ul className="space-y-4">
            {messages.map((message) => (
              <li
                key={message.id}
                className={cn(
                  "max-w-[46rem] rounded-2xl px-4 py-3",
                  message.role === "user"
                    ? "ml-auto bg-primary text-primary-foreground"
                    : message.denied
                      ? "bg-warning-soft"
                      : "bg-muted",
                )}
              >
                {message.content}
              </li>
            ))}
            {ask.isPending ? <li className="text-muted-foreground">Thinking…</li> : null}
          </ul>
        )}
      </section>

      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          send(prompt);
        }}
      >
        <label htmlFor="prompt" className="sr-only">
          Ask the AI assistant
        </label>
        <Textarea
          id="prompt"
          rows={2}
          className="flex-1"
          placeholder="e.g. Which students need extra support in Mathematics?"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
        <Button
          type="submit"
          className="h-12 sm:self-end"
          disabled={ask.isPending || !prompt.trim()}
        >
          Ask
        </Button>
      </form>
    </div>
  );
}
