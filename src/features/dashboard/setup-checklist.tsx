import { Link } from "@tanstack/react-router";
import { Check, Circle } from "lucide-react";
import { Progress } from "@/components/ui/progress";

const TASKS = [
  { label: "School profile", to: "/settings", done: true },
  { label: "Academic session and terms", to: "/academics", done: true },
  { label: "Add classes", to: "/academics", done: true },
  { label: "Add subjects", to: "/academics", done: true },
  { label: "Import students", to: "/students/import", done: false },
  { label: "Import staff", to: "/staff", done: false },
  { label: "Configure fees", to: "/finance", done: false },
];

export function SetupChecklist() {
  const complete = TASKS.filter((t) => t.done).length;
  if (complete === TASKS.length) return null;

  return (
    <section className="fn-panel p-5" aria-labelledby="setup-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="setup-heading" className="font-semibold">
          Complete your school setup
        </h2>
        <p className="text-sm text-muted-foreground">
          {complete} / {TASKS.length} complete
        </p>
      </div>
      <Progress value={(complete / TASKS.length) * 100} className="mt-3 h-2" />
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {TASKS.map((task) => (
          <li key={task.label}>
            <Link
              to={task.to}
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] transition-all duration-150 hover:bg-muted/60"
            >
              {task.done ? (
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-success-soft text-success">
                  <Check className="size-4" aria-hidden="true" />
                </span>
              ) : (
                <Circle
                  className="size-6 shrink-0 text-muted-foreground/50"
                  aria-hidden="true"
                  strokeWidth={1.5}
                />
              )}
              <span className={task.done ? "text-muted-foreground line-through" : ""}>
                {task.label}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
