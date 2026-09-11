import { Link } from "@tanstack/react-router";
import { NavIcon } from "@/components/common/icon";

export interface QuickAction {
  label: string;
  to: string;
  icon: string;
}

export function QuickActions({ actions }: { actions: QuickAction[] }) {
  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="mb-3 font-display text-[17px] font-semibold">
        Quick actions
      </h2>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {actions.map((action) => (
          <li key={action.label + action.to}>
            <Link
              to={action.to}
              className="fn-panel fn-panel-hover flex min-h-[5.5rem] flex-col justify-between gap-3 p-4"
            >
              <span aria-hidden="true" className="fn-icon-tile size-10 text-primary">
                <NavIcon name={action.icon} className="size-[1.125rem]" />
              </span>
              <span className="text-[14px] font-medium leading-snug">{action.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
