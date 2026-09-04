import { useRef, useState, type ChangeEvent } from "react";

import { Button } from "./Button";

interface FileUploadFieldProps {
  label?: string;
  hint?: string;
  accept?: string;
  disabled?: boolean;
  buttonLabel?: string;
  onFileSelected: (file: File) => void | Promise<void>;
}

// A simple multipart upload field: pick a file → hand it to onFileSelected
// (which performs the multipart POST). Shows the picked name + a busy state.
export function FileUploadField({
  label,
  hint,
  accept,
  disabled,
  buttonLabel = "Choose file",
  onFileSelected
}: FileUploadFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setName(file.name);
    setBusy(true);
    try {
      await onFileSelected(file);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="field">
      {label && <label className="field__label">{label}</label>}
      <div className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          style={{ display: "none" }}
          onChange={handleChange}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          loading={busy}
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          {buttonLabel}
        </Button>
        {name && <span className="muted text-sm">{name}</span>}
      </div>
      {hint && <div className="field__hint">{hint}</div>}
    </div>
  );
}
