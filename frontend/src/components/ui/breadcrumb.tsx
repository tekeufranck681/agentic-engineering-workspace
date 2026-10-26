import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

function Breadcrumb(props: React.ComponentProps<"nav">) {
  return <nav aria-label="Breadcrumb" {...props} />;
}
function BreadcrumbList({ className, ...props }: React.ComponentProps<"ol">) {
  return <ol className={cn("breadcrumb-list", className)} {...props} />;
}
function BreadcrumbItem({ className, ...props }: React.ComponentProps<"li">) {
  return <li className={cn("breadcrumb-item", className)} {...props} />;
}
function BreadcrumbLink({
  asChild = false,
  className,
  ...props
}: React.ComponentProps<"a"> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "a";
  return <Comp className={cn("breadcrumb-link", className)} {...props} />;
}
function BreadcrumbPage(props: React.ComponentProps<"span">) {
  return <span aria-current="page" {...props} />;
}
function BreadcrumbSeparator() {
  return (
    <li role="presentation" aria-hidden="true" className="breadcrumb-separator">
      <ChevronRight size={14} />
    </li>
  );
}
export {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
};
