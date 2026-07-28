export const normalizeSelectedExecutionIds = (ids: unknown): string[] => {
  if (!Array.isArray(ids)) {
    return [];
  }

  return [...new Set(ids.filter((id): id is string => typeof id === 'string'))];
};
