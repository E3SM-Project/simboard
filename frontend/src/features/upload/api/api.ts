import { api } from '@/api/api';

export interface ArchiveUploadValidationError {
  code: string;
  execution_dir: string;
  file_spec: string;
  location: string;
  message: string;
}

export interface ArchiveUploadValidationDetail {
  message: string;
  errors: ArchiveUploadValidationError[];
}

export interface IngestionUploadResponse {
  created_count: number;
  duplicate_count: number;
  executions: IngestionUploadExecutionSummary[];
  errors: Record<string, string>[];
}

export interface IngestionUploadExecutionSummary {
  id: string;
  case_id: string;
  case_name: string;
  execution_id: string;
}

interface UploadExecutionArchiveParams {
  file: File;
  machineName: string;
  hpcUsername?: string;
}

export const uploadExecutionArchive = async ({
  file,
  machineName,
  hpcUsername,
}: UploadExecutionArchiveParams): Promise<IngestionUploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('machine_name', machineName);

  if (hpcUsername) {
    formData.append('hpc_username', hpcUsername);
  }

  const response = await api.post<IngestionUploadResponse>('/ingestions/from-upload', formData);

  return response.data;
};
