import { clsx } from 'clsx';
import { format } from 'date-fns';
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
  const ms = end.getTime() - start.getTime();
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));

  if (days >= 365) {
    const years = Math.floor(days / 365);
    return `${years} year${years !== 1 ? 's' : ''}`;
  }

  if (days >= 30) {
    const months = Math.floor(days / 30);
    return `${months} month${months !== 1 ? 's' : ''}`;
  }

  if (days >= 1) {
    return `${days} day${days !== 1 ? 's' : ''}`;
  }

  const hours = Math.floor(ms / (1000 * 60 * 60));
  if (hours >= 1) {
    return `${hours} hour${hours !== 1 ? 's' : ''}`;
  }

  const minutes = Math.floor(ms / (1000 * 60));
  return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
};
