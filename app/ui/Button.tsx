import type { ButtonHTMLAttributes, ReactNode } from "react";
import { UI_STRINGS } from "./strings.ts";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Disables the button and shows progress; the label stays readable. */
  loading?: boolean;
  /** Why the button is disabled; shown as the title (spec 2). */
  disabledReason?: string;
  loadingLabel?: string;
  className?: string;
  children: ReactNode;
};

export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md", extra?: string): string {
  return `v-btn v-btn--${variant} v-btn--${size}${extra ? ` ${extra}` : ""}`;
}

/** Spec 2: four variants, two sizes; `loading` disables and shows progress. */
export function Button({ variant = "secondary", size = "md", loading = false, disabled, disabledReason, loadingLabel = UI_STRINGS.working, className, type = "button", title, children, ...rest }: ButtonProps) {
  const isDisabled = Boolean(disabled || loading);
  return <button
    {...rest}
    type={type}
    className={buttonClass(variant, size, className)}
    disabled={isDisabled}
    aria-busy={loading || undefined}
    title={isDisabled && disabledReason ? disabledReason : title}
  >
    {loading && <span className="v-btn__spinner" aria-hidden="true" />}
    <span className="v-btn__label">{children}</span>
    {loading && <span className="v-visually-hidden">{loadingLabel}</span>}
  </button>;
}

export type IconButtonProps = Omit<ButtonProps, "children" | "aria-label"> & {
  /** Required accessible name (spec 2). */
  label: string;
  icon: ReactNode;
};

/** Spec 2: an icon-only button always has an aria-label. */
export function IconButton({ label, icon, variant = "ghost", size = "sm", className, title, ...rest }: IconButtonProps) {
  return <Button {...rest} variant={variant} size={size} aria-label={label} title={title ?? label} className={`v-icon-btn${className ? ` ${className}` : ""}`}>
    <span aria-hidden="true">{icon}</span>
  </Button>;
}
