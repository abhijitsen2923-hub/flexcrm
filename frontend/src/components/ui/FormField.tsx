import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes
} from "react";


interface FieldWrapperProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
}


export function FieldWrapper({ label, hint, error, htmlFor, children }: FieldWrapperProps) {
  return (
    <div className="field">
      <label htmlFor={htmlFor} className="field__label">
        {label}
      </label>
      {children}
      {hint && !error && <div className="field__hint">{hint}</div>}
      {error && <div className="field__error">{error}</div>}
    </div>
  );
}


interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}


export function TextField({ label, hint, error, id, ...rest }: TextFieldProps) {
  return (
    <FieldWrapper label={label} hint={hint} error={error} htmlFor={id}>
      <input id={id} className="input" {...rest} />
    </FieldWrapper>
  );
}


interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  options: ReadonlyArray<{ value: string; label: string }>;
  placeholder?: string;
}


export function SelectField({
  label,
  hint,
  error,
  id,
  options,
  placeholder,
  ...rest
}: SelectFieldProps) {
  return (
    <FieldWrapper label={label} hint={hint} error={error} htmlFor={id}>
      <select id={id} className="select" {...rest}>
        {placeholder !== undefined && (
          <option value="">{placeholder}</option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldWrapper>
  );
}


interface TextareaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
}


export function TextareaField({ label, hint, error, id, ...rest }: TextareaFieldProps) {
  return (
    <FieldWrapper label={label} hint={hint} error={error} htmlFor={id}>
      <textarea id={id} className="textarea" {...rest} />
    </FieldWrapper>
  );
}
