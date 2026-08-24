const executionQueryKeys = {
  all: ['executions'] as const,
  pages: () => ['executions', 'page'] as const,
  page: (params: object) => ['executions', 'page', params] as const,
  casePage: (caseId: string, params: object) => ['executions', 'case', caseId, params] as const,
  caseInfinite: (caseId: string, params: object) =>
    ['executions', 'case', caseId, 'infinite', params] as const,
  options: ['executions', 'filter-options'] as const,
  detail: (id: string) => ['executions', 'detail', id] as const,
  history: (id: string) => ['executions', 'detail', id, 'history'] as const,
};

export const catalogQueryKeys = {
  overview: ['catalog', 'overview'] as const,
  cases: {
    all: ['cases'] as const,
    pages: () => ['cases', 'page'] as const,
    page: (params: object) => ['cases', 'page', params] as const,
    options: ['cases', 'filter-options'] as const,
    optionsFor: (params: object) => ['cases', 'filter-options', params] as const,
    detail: (id: string) => ['cases', 'detail', id] as const,
    history: (id: string) => ['cases', 'detail', id, 'history'] as const,
  },
  executions: executionQueryKeys,
  machines: ['machines'] as const,
  sites: ['sites'] as const,
};
