export const catalogQueryKeys = {
  overview: ['catalog', 'overview'] as const,
  cases: {
    all: ['cases'] as const,
    pages: () => ['cases', 'page'] as const,
    page: (params: object) => ['cases', 'page', params] as const,
    options: ['cases', 'filter-options'] as const,
    detail: (id: string) => ['cases', 'detail', id] as const,
  },
  simulations: {
    all: ['simulations'] as const,
    pages: () => ['simulations', 'page'] as const,
    page: (params: object) => ['simulations', 'page', params] as const,
    casePage: (caseId: string, params: object) => ['simulations', 'case', caseId, params] as const,
    caseInfinite: (caseId: string, params: object) =>
      ['simulations', 'case', caseId, 'infinite', params] as const,
    options: ['simulations', 'filter-options'] as const,
    detail: (id: string) => ['simulations', 'detail', id] as const,
  },
  machines: ['machines'] as const,
  sites: ['sites'] as const,
};
