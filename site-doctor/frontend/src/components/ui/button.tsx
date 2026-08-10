import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-display font-semibold tracking-tight transition-[background-color,color,border-color,transform,box-shadow] duration-200 ease-out disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // Solid ink. The one loud control on the page.
        default:
          "bg-ink text-paper-raised shadow-chart hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0",
        // Hairline. Sits quietly next to the solid one.
        outline:
          "border border-ink/25 bg-transparent text-ink hover:border-ink hover:bg-ink/[0.04]",
        ghost: "text-ink-2 hover:bg-ink/[0.05] hover:text-ink",
        // Inverted, for use inside the dark monitor band.
        inverse:
          "bg-paper text-ink hover:-translate-y-0.5 hover:bg-paper-raised active:translate-y-0",
        ghostInverse: "text-paper/70 hover:bg-paper/10 hover:text-paper",
        outlineInverse:
          "border border-paper/30 bg-transparent text-paper hover:border-paper hover:bg-paper/10",
        link: "text-ink underline decoration-rule underline-offset-4 hover:decoration-ink",
      },
      size: {
        default: "h-11 px-5 text-sm",
        sm: "h-9 px-3.5 text-[0.8125rem]",
        lg: "h-[3.25rem] px-7 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
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
