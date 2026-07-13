export const normalizeSelectedSimulationIds = (ids: unknown): string[] => {
  if (!Array.isArray(ids)) {
    return [];
  }

  return [...new Set(ids.filter((id): id is string => typeof id === 'string'))];
};
