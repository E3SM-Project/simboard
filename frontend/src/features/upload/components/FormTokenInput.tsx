import { useState } from 'react';

interface FormTokenInputProps {
  values: string[];
  setValues: (vals: string[]) => void;
  placeholder?: string;
}

const FormTokenInput = ({
  values,
  setValues,
  placeholder = 'Type and press Enter',
}: FormTokenInputProps) => {
  // -------------------- Local State --------------------
  const [draft, setDraft] = useState('');

  // -------------------- Handlers -----------------------
  const addToken = (v: string) => {
    const val = v.trim();
    if (!val) return;
    if (!values.includes(val)) setValues([...values, val]);
    setDraft('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addToken(draft);
    } else if (e.key === 'Backspace' && !draft && values.length) {
      e.preventDefault();
      setValues(values.slice(0, -1));
    }
  };

  // -------------------- Render --------------------
  return (
    <div className="flex min-h-10 items-center flex-wrap gap-2 rounded-md border border-gray-300 px-2 py-2 focus-within:ring-2 focus-within:ring-gray-900/10">
      {values.map((v) => (
        <span
          key={v}
          className="inline-flex items-center gap-1 rounded-full border bg-gray-50 px-2 py-0.5 text-xs"
        >
          {v}
          <button
            type="button"
            className="opacity-60 hover:opacity-100"
            onClick={() => setValues(values.filter((x) => x !== v))}
            aria-label={`Remove ${v}`}
          >
            ✕
          </button>
        </span>
      ))}
      <input
        className="flex-1 min-w-[12ch] bg-transparent outline-none text-sm"
        value={draft}
        placeholder={values.length ? '' : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => addToken(draft)}
        onKeyDown={handleKeyDown}
      />
    </div>
  );
};

export default FormTokenInput;
