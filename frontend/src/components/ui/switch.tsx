"use client";

import * as React from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

/**
 * 开关组件（shadcn 范式：forwardRef + displayName，API 兼容旧版 onChange/label）。
 * 内部复用 @radix-ui/react-switch，对外暴露 (checked, onChange, label, disabled) 调用方零改动。
 */

interface SwitchProps {
  checked?: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ checked, onChange, label, disabled, className, ...props }, ref) => (
    <SwitchPrimitives.Root
      ref={ref}
      data-slot="switch"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onCheckedChange={onChange}
      className={cn(
        "peer relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted-foreground/30",
        className,
      )}
      {...props}
    >
      <SwitchPrimitives.Thumb
        className={cn(
          "pointer-events-none block h-5 w-5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform",
          "data-[state=checked]:translate-x-[22px]",
        )}
      />
    </SwitchPrimitives.Root>
  ),
);
Switch.displayName = "Switch";

export { Switch };
