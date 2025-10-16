import { Funnel } from 'lucide-react';

import { MultiSelect } from '@/components/ui/multi-select';
import type { FilterState } from '@/pages/Browse/Browse';
import CollapsibleGroup from '@/pages/Browse/CollapsibleGroup';
import MultiSelectCheckboxGroup from '@/pages/Browse/MultiSelectCheckBoxGroup';

interface FilterPanelProps {
  appliedFilters: FilterState;
  availableFilters: FilterState;
  onChange: (next: FilterState) => void;
  machineOptions: { value: string; label: string }[];
}

const BrowseFiltersSidePanel = ({
  appliedFilters,
  availableFilters,
  onChange,
  machineOptions,
}: FilterPanelProps) => {
  // -------------------- Handlers --------------------
  const handleChange = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    const nextValue = Array.isArray(value) ? Array.from(new Set(value)) : value;

    onChange({ ...appliedFilters, [key]: nextValue });
  };

  // -------------------- Render --------------------
  return (
    <aside className="w-[360px] max-w-full bg-background border-r p-6 flex flex-col gap-6 min-h-screen border border-gray-300">
      <div className="mb-4">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          Filters <Funnel />
        </h1>
        <p className="text-base text-gray-600 mt-1">
          Use the filters below to refine your search results.
        </p>
      </div>

      {/* Scientific Goal */}
      <CollapsibleGroup
        title="Scientific Goal"
        description="Filter by high-level scientific purpose, such as campaign, experiment, or outputs."
      >
        <label className="block text-sm font-medium text-gray-700">Campaign</label>
        <MultiSelect
          options={(availableFilters.campaignId || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.campaignId || []}
          onValueChange={(next) => handleChange('campaignId', next as string[])}
          placeholder="Select campaigns"
          resetOnDefaultValueChange={true}
        />

        <label className="block text-sm font-medium text-gray-700">Experiment Type</label>
        <MultiSelect
          options={(availableFilters.experimentTypeId || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.experimentTypeId || []}
          onValueChange={(next) => handleChange('experimentTypeId', next as string[])}
          placeholder="Select experiments"
          resetOnDefaultValueChange={true}
        />

        <MultiSelectCheckboxGroup
          label="Simulation Type"
          options={availableFilters.simulationType || []}
          selected={appliedFilters.simulationType || []}
          onChange={(next) => handleChange('simulationType', next)}
        />

        <MultiSelectCheckboxGroup
          label="Initialization Type"
          options={availableFilters.initializationType || []}
          selected={appliedFilters.initializationType || []}
          onChange={(next) => handleChange('initializationType', next)}
        />

        {/* Frequency left out for now */}
      </CollapsibleGroup>

      {/* Simulation Context */}
      <CollapsibleGroup
        title="Simulation Context"
        description="Refine results based on the technical setup of the simulation."
      >
        <label className="block text-sm font-medium text-gray-700">Compset</label>
        <MultiSelect
          options={(availableFilters.compset || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.compset || []}
          onValueChange={(next) => handleChange('compset', next as string[])}
          placeholder="Select compsets"
          resetOnDefaultValueChange={true}
        />

        <label className="block text-sm font-medium text-gray-700">Grid Name</label>
        <MultiSelect
          options={(availableFilters.gridName || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.gridName || []}
          onValueChange={(next) => handleChange('gridName', next as string[])}
          placeholder="Select grid names"
          resetOnDefaultValueChange={true}
        />

        <label className="block text-sm font-medium text-gray-700">Grid Resolution</label>
        <MultiSelect
          options={(availableFilters.gridResolution || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.gridResolution || []}
          onValueChange={(next) => handleChange('gridResolution', next as string[])}
          placeholder="Select grid resolutions"
          resetOnDefaultValueChange={true}
        />
      </CollapsibleGroup>

      <CollapsibleGroup
        title="Execution Details"
        description="Filter by run status or time information."
      >
        <MultiSelectCheckboxGroup
          label="Machine"
          // Prefer id/label pairs if provided, else fall back to raw ids
          options={
            machineOptions && machineOptions.length > 0
              ? machineOptions
              : availableFilters.machineId || []
          }
          selected={appliedFilters.machineId || []}
          onChange={(next) => handleChange('machineId', next)}
        />

        <MultiSelectCheckboxGroup
          label="Compiler"
          options={availableFilters.compiler || []}
          selected={appliedFilters.compiler || []}
          onChange={(next) => handleChange('compiler', next)}
        />
        <MultiSelectCheckboxGroup
          label="Status"
          options={availableFilters.status || []}
          selected={appliedFilters.status || []}
          onChange={(next) => handleChange('status', next)}
          renderOptionLabel={(option) =>
            typeof option === 'string'
              ? option.charAt(0).toUpperCase() + option.slice(1)
              : option.label
          }
        />
      </CollapsibleGroup>

      {/* Provenance*/}
      <CollapsibleGroup title="Provenance" description="Filter by provenance information.">
        <label className="block text-sm font-medium text-gray-700">Git Version/Tag</label>
        <MultiSelect
          options={(availableFilters.gitTag || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.gitTag || []}
          onValueChange={(next) => handleChange('gitTag', next as string[])}
          placeholder="Select git tags"
          resetOnDefaultValueChange={true}
        />

        <label className="block text-sm font-medium text-gray-700">Created By</label>
        <MultiSelect
          options={(availableFilters.createdBy || []).map((id) => ({
            value: id,
            label: id,
          }))}
          defaultValue={appliedFilters.createdBy || []}
          onValueChange={(next) => handleChange('createdBy', next as string[])}
          placeholder="Select creators"
          resetOnDefaultValueChange={true}
        />
      </CollapsibleGroup>
    </aside>
  );
};

export default BrowseFiltersSidePanel;
