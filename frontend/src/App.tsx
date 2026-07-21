import { useEffect, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { NavBar } from '@/components/layout/NavBar';
import { normalizeSelectedSimulationIds } from '@/components/shared/normalizeSelectedSimulationIds';
import { useMachines } from '@/features/machines/hooks/useMachines';
import { useSites } from '@/features/sites/hooks/useSites';
import { CaseCompareRoute } from '@/routes/CaseCompareRoute';
import { AppRoutes } from '@/routes/routes';

import { Toaster } from './components/ui/toaster';

const App = () => {
  // -------------------- Constants --------------------
  const LOCAL_STORAGE_KEY = 'selectedSimulationIds';

  // -------------------- Local State --------------------
  const { data: machines = [] } = useMachines();
  const { data: sites = [] } = useSites();

  const [selectedSimulationIds, setSelectedSimulationIds] = useState<string[]>(() => {
    const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
    return stored ? normalizeSelectedSimulationIds(JSON.parse(stored)) : [];
  });
  const [selectedCaseSimulationIdsByCase, setSelectedCaseSimulationIdsByCase] = useState<
    Record<string, string[]>
  >({});

  const setSelectedCaseSimulationIdsForCase = (caseId: string, ids: string[]) => {
    const nextIds = normalizeSelectedSimulationIds(ids);

    setSelectedCaseSimulationIdsByCase((current) => {
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
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(selectedSimulationIds));
  }, [selectedSimulationIds]);

  // -------------------- Render --------------------
  return (
    <BrowserRouter>
      <NavBar />
      <AppRoutes
        machines={machines}
        sites={sites}
        renderCaseCompareSection={({ onClose }) => (
          <CaseCompareRoute
            onClose={onClose}
            selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
            setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
            setSelectedSimulationIds={setSelectedSimulationIds}
          />
        )}
        selectedCaseSimulationIdsByCase={selectedCaseSimulationIdsByCase}
        setSelectedCaseSimulationIdsForCase={setSelectedCaseSimulationIdsForCase}
        selectedSimulationIds={selectedSimulationIds}
        setSelectedSimulationIds={setSelectedSimulationIds}
      />
      <Toaster />
    </BrowserRouter>
  );
};

export default App;
