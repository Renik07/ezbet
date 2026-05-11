"use client";

import { useFormStatus } from "react-dom";

type PendingSubmitButtonProps = {
  idleLabel: string;
  pendingLabel: string;
  className: string;
  formAction?: (formData: FormData) => void | Promise<void>;
  disabled?: boolean;
};

export function PendingSubmitButton({
  idleLabel,
  pendingLabel,
  className,
  formAction,
  disabled = false
}: PendingSubmitButtonProps) {
  const { pending } = useFormStatus();
  const isDisabled = pending || disabled;

  return (
    <button
      className={`${className} ${pending ? "is-pending" : ""}`}
      type="submit"
      formAction={formAction}
      disabled={isDisabled}
    >
      {pending ? pendingLabel : idleLabel}
    </button>
  );
}
