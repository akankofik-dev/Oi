import { request } from "../request";
import type {
  OiCronRow,
  OiCronCreateBody,
  OiCronPatchBody,
} from "../types";

export interface OiCronSettings {
  timezone: string;
}

export interface CronTaskExamples {
  zh?: string[];
  en?: string[];
}

export const octopCronApi = {
  settings: () => request<OiCronSettings>("/cron/settings"),

  list: (agentId: string) => request<OiCronRow[]>(`/agents/${agentId}/cron`),

  create: (agentId: string, body: OiCronCreateBody) =>
    request<OiCronRow>(`/agents/${agentId}/cron`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  get: (agentId: string, cronId: string) =>
    request<OiCronRow>(`/agents/${agentId}/cron/${cronId}`),

  patch: (agentId: string, cronId: string, body: OiCronPatchBody) =>
    request<OiCronRow>(`/agents/${agentId}/cron/${cronId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (agentId: string, cronId: string) =>
    request<void>(`/agents/${agentId}/cron/${cronId}`, { method: "DELETE" }),

  runNow: (agentId: string, cronId: string) =>
    request<void>(`/agents/${agentId}/cron/${cronId}/run-now`, {
      method: "POST",
    }),
};
