import { useEffect, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { NavBar } from '@/components/layout/NavBar';
import { normalizeSelectedExecutionIds } from '@/components/shared/normalizeSelectedExecutionIds';
import { useMachines } from '@/features/machines/hooks/useMachines';
import { useSites } from '@/features/sites/hooks/useSites';
import { CaseCompareRoute } from '@/routes/CaseCompareRoute';
import { AppRoutes } from '@/routes/routes';

import { Toaster } from './components/ui/toaster';

const App = () => {
  // -------------------- Constants --------------------
  const LOCAL_STORAGE_KEY = 'selectedExecutionIds';

  // -------------------- Local State --------------------
  const { data: machines = [] } = useMachines();
  const { data: sites = [] } = useSites();

  const [selectedExecutionIds, setSelectedExecutionIds] = useState<string[]>(() => {
    const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
    return stored ? normalizeSelectedExecutionIds(JSON.parse(stored)) : [];
  });
  const [selectedCaseExecutionIdsByCase, setSelectedCaseExecutionIdsByCase] = useState<
    Record<string, string[]>
  >({});

  const setSelectedCaseExecutionIdsForCase = (caseId: string, ids: string[]) => {
    const nextIds = normalizeSelectedExecutionIds(ids);

    setSelectedCaseExecutionIdsByCase((current) => {
      if (nextIds.length === 0) {
        if (!(caseId in current)) {
          return current;
        }

        const nextState = { ...current };
        delete nextState[caseId];
        return nextState;
      }

      return {
        ...current,
        [caseId]: nextIds,
      };
    });
  };

  // -------------------- Effects --------------------
  useEffect(() => {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(selectedExecutionIds));
  }, [selectedExecutionIds]);

  // -------------------- Render --------------------
  return (
    <BrowserRouter>
      <NavBar />
      <AppRoutes
        machines={machines}
        sites={sites}
        renderCaseCompareSection={({ caseId, onClose }) => (
          <CaseCompareRoute
            caseId={caseId}
            onClose={onClose}
            selectedCaseExecutionIdsByCase={selectedCaseExecutionIdsByCase}
            setSelectedCaseExecutionIdsForCase={setSelectedCaseExecutionIdsForCase}
            setSelectedExecutionIds={setSelectedExecutionIds}
          />
        )}
        selectedCaseExecutionIdsByCase={selectedCaseExecutionIdsByCase}
        setSelectedCaseExecutionIdsForCase={setSelectedCaseExecutionIdsForCase}
        selectedExecutionIds={selectedExecutionIds}
        setSelectedExecutionIds={setSelectedExecutionIds}
      />
      <Toaster />
    </BrowserRouter>
  );
};

export default App;
