"use client";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function RightInspector({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    function dismiss(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", dismiss);
    return () => document.removeEventListener("keydown", dismiss);
  }, [onClose]);
  return (
    <aside className="inspector" role="dialog" aria-label={title}>
      <div className="inspector-heading">
        <h2>{title}</h2>
        <Button
          ref={close}
          variant="ghost"
          aria-label="Close project details"
          onClick={onClose}
        >
          <X size={16} aria-hidden="true" />
        </Button>
      </div>
      {children}
    </aside>
  );
}
