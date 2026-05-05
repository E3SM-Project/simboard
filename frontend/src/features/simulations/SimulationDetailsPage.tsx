import { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';

import { resolvePaceExecution } from '@/features/simulations/api/api';
import { SimulationDetailsView } from '@/features/simulations/components/SimulationDetailsView';
import { useSimulation } from '@/features/simulations/hooks/useSimulation';

export const SimulationDetailsPage = () => {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const { data: simulation, loading, error } = useSimulation(id ?? '');
  const [paceExperimentId, setPaceExperimentId] = useState<string | null>(null);
  const [isResolvingPace, setIsResolvingPace] = useState(false);
  const [paceResolutionAttempted, setPaceResolutionAttempted] = useState(false);

  const state = location.state as { from?: string } | null;
  const backHref = typeof state?.from === 'string' ? state.from : '/browse';
  const normalizedBackHref = backHref.split(/[?#]/)[0];
  const backLabel = normalizedBackHref.startsWith('/cases/')
    ? 'Back to Case'
    : normalizedBackHref === '/cases'
      ? 'Back to Cases'
      : normalizedBackHref.startsWith('/simulations')
        ? 'Back to Simulations'
        : 'Back to Runs';
  const executionId = simulation?.executionId?.trim() ?? '';

  useEffect(() => {
    if (!executionId) {
      setPaceExperimentId(null);
      setIsResolvingPace(false);
      setPaceResolutionAttempted(false);
      return;
    }

    let cancelled = false;
    setPaceExperimentId(null);
    setIsResolvingPace(true);
    setPaceResolutionAttempted(false);

    resolvePaceExecution(executionId)
      .then((result) => {
        if (!cancelled) {
          setPaceExperimentId(result.experimentId?.trim() || null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPaceExperimentId(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsResolvingPace(false);
          setPaceResolutionAttempted(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [executionId]);

  if (!id) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Invalid simulation ID</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Loading simulation details…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (!simulation) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">Simulation not found</div>
      </div>
    );
  }

  const paceLink = executionId
    ? paceExperimentId
      ? {
          href: `https://pace.ornl.gov/exp-details/${encodeURIComponent(paceExperimentId)}`,
          label: 'Open in PACE',
        }
      : {
          href: `https://pace.ornl.gov/search/${encodeURIComponent(executionId)}`,
          label: 'Search in PACE',
        }
    : null;

  return (
    <SimulationDetailsView
      simulation={simulation}
      backHref={backHref}
      backLabel={backLabel}
      paceLink={paceLink}
      isResolvingPace={isResolvingPace}
      showPaceFallbackInfo={paceResolutionAttempted && !paceExperimentId}
    />
  );
};
