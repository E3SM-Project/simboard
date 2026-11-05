export const getTextDiffParts = (
  value: string,
  reference: string | null,
): Array<{ text: string; changed: boolean }> => {
  if (value === '') return [];
  if (value === reference) return [{ text: value, changed: false }];
  const tokens = value.split(/([_%./\s-]+)/).filter(Boolean);
  const referenceTokens = (reference ?? '').split(/([_%./\s-]+)/).filter(Boolean);
  // Bound work for unusually large metadata values; keep their text intact.
  if (tokens.length * referenceTokens.length > 100_000) {
    return [{ text: value, changed: true }];
  }
  const lengths = Array.from(
    { length: referenceTokens.length + 1 },
    () => new Uint32Array(tokens.length + 1),
  );
  for (let i = referenceTokens.length - 1; i >= 0; i--) {
    for (let j = tokens.length - 1; j >= 0; j--) {
      lengths[i][j] =
        referenceTokens[i] === tokens[j]
          ? 1 + lengths[i + 1][j + 1]
          : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const unchanged = new Set<number>();
  let i = 0;
  let j = 0;
  while (i < referenceTokens.length && j < tokens.length) {
    if (referenceTokens[i] === tokens[j]) {
      unchanged.add(j);
      i++;
      j++;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  const parts: Array<{ text: string; changed: boolean }> = [];
  tokens.forEach((text, index) => {
    const changed = !unchanged.has(index);
    const previous = parts.at(-1);
    if (previous?.changed === changed) previous.text += text;
    else parts.push({ text, changed });
  });
  // A deletion has no new token to mark. Highlight the remaining value instead.
  if (parts.every((part) => !part.changed)) return [{ text: value, changed: true }];

  return parts;
};
