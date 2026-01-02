import { CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react';

interface FormSectionProps {
  title: string;
  isOpen: boolean;
  onToggle: () => void;
  requiredCount?: number;
  satisfiedCount?: number;
  children: React.ReactNode;
}

export const FormSection = ({
  title,
  isOpen,
  onToggle,
  requiredCount,
  satisfiedCount,
  children,
}: FormSectionProps) => {
  const done = requiredCount && satisfiedCount !== undefined && satisfiedCount >= requiredCount;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden mb-6">
      <button
        type="button"
        className="w-full text-left px-5 py-3 bg-gray-50/80 backdrop-blur flex items-center justify-between border-b"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          {isOpen ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          <span className="font-semibold">{title}</span>
          {requiredCount ? (
            <span className="text-xs text-muted-foreground">
              ({Math.min(satisfiedCount ?? 0, requiredCount)} of {requiredCount} required)
            </span>
          ) : null}
        </div>
        {done ? <CheckCircle2 className="h-5 w-5 text-emerald-500" /> : null}
      </button>
      {isOpen ? <div className="px-5 py-4">{children}</div> : null}
    </div>
  );
};
