import { clsx } from 'clsx';
import {
  addDays,
  addHours,
  addMonths,
  addYears,
  differenceInDays,
  differenceInHours,
  differenceInMinutes,
  differenceInMonths,
  differenceInYears,
  format,
} from 'date-fns';
import { twMerge } from 'tailwind-merge';

export const cn = (...inputs: unknown[]) => twMerge(clsx(inputs));

/**
 * Formats a given date into an ISO-like string with the format 'yyyy-MM-dd HH:mm:ss'.
 *
 * @param date - The date to format. Can be a string, number, or Date object.
 * @returns A formatted date string in the 'yyyy-MM-dd HH:mm:ss' format.
 *
 * @example
 * ```typescript
 * const formattedDate = formatDate(new Date('2023-10-05T14:48:00.000Z'));
 * console.log(formattedDate); // Output: '2023-10-05 14:48:00'
 * ```
 */
export const formatDate = (date: string | number | Date): string =>
  format(new Date(date), 'yyyy-MM-dd HH:mm:ss');

interface ModelDateParts {
  day: number;
  iso: string;
  month: number;
  year: number;
}

const MILLISECONDS_PER_DAY = 86_400_000;

const toUtcDate = ({ day, month, year }: ModelDateParts): Date => {
  const value = new Date(0);
  value.setUTCHours(0, 0, 0, 0);
  value.setUTCFullYear(year, month - 1, day);
  return value;
};

const toEpochDay = (value: ModelDateParts): number =>
  Math.floor(toUtcDate(value).getTime() / MILLISECONDS_PER_DAY);

const daysInMonth = (year: number, month: number): number => {
  const value = new Date(0);
  value.setUTCHours(0, 0, 0, 0);
  value.setUTCFullYear(year, month, 0);
  return value.getUTCDate();
};

const addModelMonths = (value: ModelDateParts, months: number): ModelDateParts => {
  const absoluteMonth = value.year * 12 + value.month - 1 + months;
  const year = Math.floor(absoluteMonth / 12);
  const month = (((absoluteMonth % 12) + 12) % 12) + 1;
  const day = Math.min(value.day, daysInMonth(year, month));

  return {
    day,
    iso: `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    month,
    year,
  };
};

const parseModelDate = (value: string): ModelDateParts | null => {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/.exec(value);
  if (!match) return null;

  const [, yearText, monthText, dayText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const utcDate = toUtcDate({ day, iso: '', month, year });

  if (
    utcDate.getUTCFullYear() !== year ||
    utcDate.getUTCMonth() !== month - 1 ||
    utcDate.getUTCDate() !== day
  ) {
    return null;
  }

  return { day, iso: `${yearText}-${monthText}-${dayText}`, month, year };
};

export const formatModelDate = (value?: string | null): string => {
  if (!value) return '—';
  return parseModelDate(value)?.iso ?? '—';
};

export const compareModelDates = (left: string, right: string): number =>
  formatModelDate(left).localeCompare(formatModelDate(right));

/**
 * Calculates the duration between two dates and returns it as a human-readable string.
 * The duration is expressed in years, months, days, hours, or minutes, depending on the difference.
 *
 * @param simulationStartDate - The start date of the simulation. Can be a string, number, or Date object.
 * @param simulationEndDate - The end date of the simulation. Can be a string, number, or Date object.
 * @returns A string representing the duration between the two dates in the largest appropriate unit.
 *
 * @example
 * ```typescript
 * const duration1 = getSimulationDuration('2022-01-01', '2023-01-01');
 * console.log(duration1); // "1 year"
 *
 * const duration2 = getSimulationDuration('2023-01-01', '2023-02-15');
 * console.log(duration2); // "1 month"
 *
 * const duration3 = getSimulationDuration('2023-01-01T00:00:00', '2023-01-01T12:00:00');
 * console.log(duration3); // "12 hours"
 * ```
 */
export const getSimulationDuration = (
  simulationStartDate: string | number | Date,
  simulationEndDate: string | number | Date,
): string => {
  const start = new Date(simulationStartDate);
  const end = new Date(simulationEndDate);
  const parts: string[] = [];
  let remainder = start;

  const years = differenceInYears(end, remainder);
  if (years > 0) {
    parts.push(`${years} year${years !== 1 ? 's' : ''}`);
    remainder = addYears(remainder, years);
  }

  const months = differenceInMonths(end, remainder);
  if (months > 0) {
    parts.push(`${months} month${months !== 1 ? 's' : ''}`);
    remainder = addMonths(remainder, months);
  }

  const days = differenceInDays(end, remainder);
  if (days > 0) {
    parts.push(`${days} day${days !== 1 ? 's' : ''}`);
    remainder = addDays(remainder, days);
  }

  const hours = differenceInHours(end, remainder);
  if (hours > 0) {
    parts.push(`${hours} hour${hours !== 1 ? 's' : ''}`);
    remainder = addHours(remainder, hours);
  }

  const minutes = differenceInMinutes(end, remainder);
  if (minutes > 0 || parts.length === 0) {
    parts.push(`${minutes} minute${minutes !== 1 ? 's' : ''}`);
  }

  return parts.slice(0, 2).join(', ');
};

export const getModelDateDuration = (startDate: string, endDate: string): string => {
  const start = parseModelDate(startDate);
  const end = parseModelDate(endDate);
  if (!start || !end) throw new RangeError('Invalid model date');

  const endEpochDay = toEpochDay(end);
  const totalDays = endEpochDay - toEpochDay(start);
  if (totalDays < 0) return `${totalDays} day${totalDays === -1 ? '' : 's'}`;

  const parts: string[] = [];
  let remainder = start;
  let years = end.year - start.year;
  if (toEpochDay(addModelMonths(start, years * 12)) > endEpochDay) years -= 1;
  if (years > 0) {
    parts.push(`${years} year${years === 1 ? '' : 's'}`);
    remainder = addModelMonths(remainder, years * 12);
  }

  let months = (end.year - remainder.year) * 12 + end.month - remainder.month;
  if (toEpochDay(addModelMonths(remainder, months)) > endEpochDay) months -= 1;
  if (months > 0) {
    parts.push(`${months} month${months === 1 ? '' : 's'}`);
    remainder = addModelMonths(remainder, months);
  }

  const days = endEpochDay - toEpochDay(remainder);
  if (days > 0) parts.push(`${days} day${days === 1 ? '' : 's'}`);
  if (parts.length === 0) parts.push('0 days');

  return parts.slice(0, 2).join(', ');
};
