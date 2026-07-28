import type {
  ExternalLinkIn,
  ExternalLinkKind,
  ExternalLinkOut,
  ExternalLinkOwnerType,
} from '@/types';

export type EditableResourceField = 'kind' | 'label' | 'value';

export type ResourceRowFieldErrors = Partial<Record<EditableResourceField, string>>;

export type ValidationDetail = {
  loc: Array<string | number>;
  msg: string;
};

export type EditableLinkRow = {
  kind: ExternalLinkKind;
  label: string;
  value: string;
};

export const EXTERNAL_LINK_KIND_OPTIONS: ReadonlyArray<{
  value: ExternalLinkKind;
  label: string;
}> = [
  { value: 'diagnostic', label: 'Diagnostic' },
  { value: 'performance', label: 'Performance' },
  { value: 'docs', label: 'Docs' },
  { value: 'other', label: 'Other' },
];

export const formatLinkKindLabel = (kind: ExternalLinkKind): string =>
  EXTERNAL_LINK_KIND_OPTIONS.find((option) => option.value === kind)?.label ?? kind;

export const normalizeOptionalText = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed || null;
};

export const toEditableLinkRows = (
  links: ExternalLinkOut[],
  ownerType?: ExternalLinkOwnerType,
): EditableLinkRow[] =>
  links
    .filter((link) => ownerType == null || link.ownerType === ownerType)
    .map((link) => ({
      kind: link.kind,
      label: link.label ?? '',
      value: link.url,
    }));

export const normalizeLinkRows = (rows: EditableLinkRow[]): ExternalLinkIn[] =>
  rows.map((row) => ({
    kind: row.kind,
    url: row.value.trim(),
    label: normalizeOptionalText(row.label),
  }));

export const createEmptyRowErrors = (count: number): ResourceRowFieldErrors[] =>
  Array.from({ length: count }, () => ({}));

export const getClientLinkRowErrors = (
  linkRows: EditableLinkRow[],
): ResourceRowFieldErrors[] =>
  linkRows.map((row) => (row.value.trim().length === 0 ? { value: 'Link URL is required.' } : {}));

const normalizeValidationLoc = (loc: Array<string | number>): Array<string | number> =>
  loc[0] === 'body' ? loc.slice(1) : loc;

const toEditableField = (field: string): EditableResourceField | null => {
  if (field === 'url' || field === 'uri') {
    return 'value';
  }

  if (field === 'kind' || field === 'label') {
    return field;
  }

  return null;
};

const toValidationPathLabel = (loc: Array<string | number>): string => {
  const normalizedLoc = normalizeValidationLoc(loc);
  if (normalizedLoc.length === 0) {
    return 'Validation error';
  }

  return normalizedLoc
    .map((segment) => (typeof segment === 'number' ? `${segment + 1}` : segment))
    .join(' > ');
};

export const mapLinkSaveValidationErrors = (
  validationDetails: ValidationDetail[],
  linkCount: number,
) => {
  const rowErrors = createEmptyRowErrors(linkCount);
  const unmappedMessages: string[] = [];
  let hasMappedLinkValueError = false;

  for (const detail of validationDetails) {
    const loc = normalizeValidationLoc(detail.loc);
    const [resourceName, rowIndex, fieldName] = loc;

    if (
      resourceName === 'links' &&
      typeof rowIndex === 'number' &&
      rowIndex >= 0 &&
      rowIndex < linkCount &&
      typeof fieldName === 'string'
    ) {
      const field = toEditableField(fieldName);
      if (field) {
        rowErrors[rowIndex] = {
          ...rowErrors[rowIndex],
          [field]: detail.msg,
        };
        hasMappedLinkValueError ||= field === 'value';
        continue;
      }
    }

    unmappedMessages.push(`${toValidationPathLabel(detail.loc)}: ${detail.msg}`);
  }

  return {
    rowErrors,
    unmappedMessages,
    hasMappedLinkValueError,
  };
};

export const hasAnyResourceRowErrors = (rowErrors: ResourceRowFieldErrors[]): boolean =>
  rowErrors.some((row) => Object.keys(row).length > 0);

export const areResourceListsEqual = (left: unknown, right: unknown): boolean =>
  JSON.stringify(left) === JSON.stringify(right);
