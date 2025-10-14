import type { FilterState } from '@/pages/Browse/Browse';
import CollapsibleGroup from '@/pages/Browse/CollapsibleGroup';
import MultiSelectCheckboxGroup from '@/pages/Browse/MultiSelectCheckBoxGroup';
interface FilterPanelProps {
  appliedFilters: FilterState;
  availableFilters: FilterState; // still carries raw string values for non-FK filters
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
    <aside className="w-[360px] max-w-full bg-background border-r p-6 flex flex-col gap-6 min-h-screen">
      {/* Scientific Goal */}
      <CollapsibleGroup
        title="Scientific Goal"
        description="Filter by high-level scientific purpose, such as campaign, experiment, or outputs."
      >
        <MultiSelectCheckboxGroup
          label="Campaign"
          options={availableFilters.campaignId || []}
          selected={appliedFilters.campaignId || []}
          onChange={(next) => handleChange('campaignId', next)}
        />

        <MultiSelectCheckboxGroup
          label="Experiment"
          options={availableFilters.experimentTypeId || []}
          selected={appliedFilters.experimentTypeId || []}
          onChange={(next) => handleChange('experimentTypeId', next)}
        />

        <MultiSelectCheckboxGroup
          label="Variables"
          options={availableFilters.variables || []}
          selected={appliedFilters.variables || []}
          onChange={(next) => handleChange('variables', next)}
        />

        {/* Frequency left out for now */}
      </CollapsibleGroup>

      {/* Simulation Context */}
      <CollapsibleGroup
        title="Simulation Context"
        description="Refine results based on the technical setup of the simulation."
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
          label="Grid Name"
          options={availableFilters.gridName || []}
          selected={appliedFilters.gridName || []}
          onChange={(next) => handleChange('gridName', next)}
        />

        <MultiSelectCheckboxGroup
          label="Version / Tag"
          options={availableFilters.gitTag || []}
          selected={appliedFilters.gitTag || []}
          onChange={(next) => handleChange('gitTag', next)}
        />
      </CollapsibleGroup>

      <CollapsibleGroup
        title="Execution Details"
        description="Filter by run status or time information."
      >
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
        {/* Date pickers can go here later */}
      </CollapsibleGroup>

      {/* Metadata */}
      <CollapsibleGroup title="Metadata" description="Filter by upload information.">
        <div>{/* Upload date range UI placeholder */}</div>
      </CollapsibleGroup>
    </aside>
  );
};

export default BrowseFiltersSidePanel;
