import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
const buttonVariants = cva(
  "inline-flex shrink-0 select-none items-center justify-center gap-2 rounded-md border border-transparent text-[13px] font-medium tracking-[-0.005em] outline-none transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out focus-visible:ring-[3px] focus-visible:ring-ring/35 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0 [&_svg]:transition-transform [&_svg]:duration-150",
  {
    variants: {
      variant: {
        default: "border-[#1e50c9] bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.16),0_1px_2px_rgb(15_23_42/0.14)] hover:bg-[var(--primary-hover)] active:shadow-[inset_0_1px_2px_rgb(0_0_0/0.18)]",
        outline: "border-input bg-card shadow-[0_1px_1px_rgb(0_0_0/0.04)] hover:border-[#c2c2c9] hover:bg-muted",
        ghost: "hover:bg-muted",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 gap-1.5 px-2.5 text-xs",
        lg: "h-11 gap-2.5 px-5 text-[14px]",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);
function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      data-variant={variant ?? "default"}
      data-size={size ?? "default"}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}
export { Button, buttonVariants };
