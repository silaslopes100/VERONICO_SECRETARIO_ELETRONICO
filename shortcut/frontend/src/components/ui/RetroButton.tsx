import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "danger" | "ghost" | "success";

interface RetroButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
  children?: ReactNode;
}

/** Botão com aparência de janela Windows/MSN (borda dupla, gradiente). */
export function RetroButton({
  variant = "primary",
  icon,
  children,
  className = "",
  ...rest
}: RetroButtonProps) {
  return (
    <button
      type="button"
      className={`retro-btn retro-btn--${variant} ${className}`.trim()}
      {...rest}
    >
      {icon && <span className="retro-btn__icon">{icon}</span>}
      {children}
    </button>
  );
}
