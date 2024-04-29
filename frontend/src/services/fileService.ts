import { getSettingOrDefault } from "./settingsService";

export type WorkspaceFile = {
  name: string;
  children?: WorkspaceFile[];
};

export async function selectFile(file: string): Promise<string> {
  const workspace = getSettingOrDefault("WORKSPACE");
  const res = await fetch(
    `/api/select-file?workspace=${workspace}&file=${file}`,
  );
  const data = await res.json();
  if (res.status !== 200) {
    throw new Error(data.error);
  }
  return data.code as string;
}

export async function uploadFile(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/upload-file", {
    method: "POST",
    body: formData,
  });

  const data = await res.json();

  if (res.status !== 200) {
    throw new Error(data.error || "Failed to upload file.");
  }
}

export async function getWorkspace(): Promise<WorkspaceFile> {
  const workspace = getSettingOrDefault("WORKSPACE");
  const res = await fetch(`/api/refresh-files?workspace=${workspace}`);
  const data = await res.json();
  return data as WorkspaceFile;
}
