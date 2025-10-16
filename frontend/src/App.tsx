import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { useMachines, useSimulations } from '@/api/simulation';
import NavBar from '@/components/layout/NavBar';
import { AppRoutes } from '@/routes/routes';

const App = () => {
  // -------------------- Constants --------------------
  const LOCAL_STORAGE_KEY = 'selectedSimulationIds';

  // -------------------- Local State --------------------
  const queryClient = useMemo(() => new QueryClient(), []);

  // Fetch simulations data using custom hook.
  const rawSimulations = useSimulations();
  const machines = useMachines();

  const simulations = useMemo(() => {
    if (!rawSimulations.data || !machines.data) return [];

    return rawSimulations.data.map((simulation) => ({
      ...simulation,
      machine: machines.data.find((machine) => machine.id === simulation.machineId),
    }));
  }, [rawSimulations.data, machines.data]);

  const [selectedSimulationIds, setSelectedSimulationIds] = useState<string[]>(() => {
    const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  });

  const selectedSimulations = useMemo(
    () => (simulations ?? []).filter((item) => selectedSimulationIds.includes(item.id)),
    [simulations, selectedSimulationIds],
  );
  // -------------------- Effects --------------------
  useEffect(() => {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(selectedSimulationIds));
  }, [selectedSimulationIds]);

  // -------------------- Render --------------------
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <NavBar selectedSimulationIds={selectedSimulationIds} />
        <AppRoutes
          // FIXME: Fix type annotations for AppRoutes
          simulations={simulations}
          machines={machines.data}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          selectedSimulations={selectedSimulations}
        />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
