export interface ReadableCaseIdentity {
  machineName: string;
  hpcUsername: string;
  caseName: string;
}

export interface ReadableExecutionIdentity extends ReadableCaseIdentity {
  executionId: string;
}

const encodePathSegment = (value: string) => encodeURIComponent(value);

export const caseDetailsPath = ({
  machineName,
  hpcUsername,
  caseName,
}: ReadableCaseIdentity): string =>
  `/cases/${encodePathSegment(machineName)}/${encodePathSegment(hpcUsername)}/${encodePathSegment(caseName)}`;

export const executionDetailsPath = ({
  machineName,
  hpcUsername,
  caseName,
  executionId,
}: ReadableExecutionIdentity): string =>
  `${caseDetailsPath({ machineName, hpcUsername, caseName })}/${encodePathSegment(executionId)}`;
