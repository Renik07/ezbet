"use client";

import { useFormStatus } from "react-dom";

type PendingSubmitButtonProps = {
  idleLabel: string;
  pendingLabel: string;
  className: string;
  formAction?: (formData: FormData) => void | Promise<void>;
};

export function PendingSubmitButton({
  idleLabel,
  pendingLabel,
  className,
  formAction
}: PendingSubmitButtonProps) {
  const { pending } = useFormStatus();

  return (
    <button
      className={`${className} ${pending ? "is-pending" : ""}`}
      type="submit"
      formAction={formAction}
      disabled={pending}
    >
      {pending ? pendingLabel : idleLabel}
    </button>
  );
}
