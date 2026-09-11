import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium cursor-pointer transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[0_6px_16px_-6px_oklch(0.31_0.02_250/0.55),inset_0_1px_0_oklch(1_0_0/0.1)] hover:bg-[#273850] hover:shadow-[0_10px_24px_-8px_oklch(0.31_0.02_250/0.6),inset_0_1px_0_oklch(1_0_0/0.12)] hover:-translate-y-px active:translate-y-0 active:scale-[0.98]",
        destructive:
          "bg-destructive text-destructive-foreground shadow-[0_6px_14px_-6px_oklch(0.53_0.1_30/0.5),inset_0_1px_0_oklch(1_0_0/0.1)] hover:bg-destructive/90 hover:-translate-y-px active:translate-y-0 active:scale-[0.98]",
        outline:
          "border border-input/70 bg-surface/70 text-foreground shadow-[inset_1px_1px_2px_oklch(0.31_0.02_250/0.05)] hover:bg-accent/60 hover:text-accent-foreground hover:border-input active:scale-[0.98]",
        secondary:
          "bg-secondary text-secondary-foreground shadow-[6px_6px_14px_oklch(0.31_0.02_250/0.09),-6px_-6px_14px_oklch(1_0_0/0.85),inset_0_1px_0_oklch(1_0_0/0.6)] hover:shadow-[8px_8px_18px_oklch(0.31_0.02_250/0.11),-6px_-6px_14px_oklch(1_0_0/0.9),inset_0_1px_0_oklch(1_0_0/0.6)] hover:-translate-y-px active:translate-y-0 active:scale-[0.98]",
        ghost: "text-foreground/80 hover:bg-accent/50 hover:text-foreground active:scale-[0.98]",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-lg px-3 text-xs",
        lg: "h-12 rounded-xl px-7 text-[15px]",
        icon: "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
export type { VariantProps };
