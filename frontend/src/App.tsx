import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { NavBar } from '@/components/layout/NavBar';
import { useMachines } from '@/features/machines/hooks/useMachines';
import { useSimulations } from '@/features/simulations/hooks/useSimulations';
import { AppRoutes } from '@/routes/routes';

import { Toaster } from './components/ui/toaster';

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
          simulations={simulations}
          machines={machines.data}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          selectedSimulations={selectedSimulations}
        />
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  );
};

export default App;
