interface ReviewSectionProps {
  title: string;
  children: React.ReactNode;
}

export const ReviewSection = ({ title, children }: ReviewSectionProps) => {
  return (
    <div>
      <div className="border-b-2 border-gray-300 pb-1 mb-2">
        <span className="uppercase tracking-wider text-xs font-bold text-gray-500">{title}</span>
      </div>
      {children}
    </div>
  );
};
