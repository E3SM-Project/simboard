interface ReviewLinkListProps {
  links: { label: string; url: string }[];
}

export const ReviewLinkList = ({ links }: ReviewLinkListProps) => {
  if (!Array.isArray(links)) {
    return '—';
  }

  const validLinks = links.filter((link) => link.label && link.url);

  if (validLinks.length === 0) {
    return '—';
  }

  return (
    <ul className="list-disc ml-6">
      {validLinks.map((link, idx) => (
        <li key={idx}>
          <span className="font-medium">{link.label}:</span>{' '}
          <a
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline"
          >
            {link.url}
          </a>
        </li>
      ))}
    </ul>
  );
};
