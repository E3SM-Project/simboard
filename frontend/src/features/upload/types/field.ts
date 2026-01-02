import { SimulationCreateForm } from '@/types/simulation';

export type FieldType =
  | 'select'
  | 'text'
  | 'number'
  | 'checkbox'
  | 'multiselect'
  | 'textarea'
  | 'date'
  | 'url';

export interface FieldOption {
  value: string;
  label: string;
}

export type RenderableField<TRender = React.ReactNode> = {
  name: keyof SimulationCreateForm;
  label: string;
  type: FieldType;
  placeholder?: string;
  required?: boolean;
  options?: FieldOption[];
  renderValue?: (value: string) => TRender;
};
