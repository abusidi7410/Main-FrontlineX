import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-xl border border-input/70 bg-surface/70 px-3.5 py-2 text-sm shadow-[inset_2px_2px_5px_oklch(0.31_0.02_250/0.06),inset_-1px_-1px_3px_oklch(1_0_0/0.7)] transition-all duration-200 placeholder:text-muted-foreground/80 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground hover:border-input/90 focus-visible:outline-none focus-visible:border-primary/45 focus-visible:bg-white focus-visible:shadow-[inset_2px_2px_5px_oklch(0.31_0.02_250/0.04),inset_-1px_-1px_3px_oklch(1_0_0/0.6),0_0_0_3px_oklch(0.31_0.02_250/0.07)] focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
