"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  ContributionResponse,
  ContributionStatistics,
  ContributionStreak,
} from "@/lib/types";

export function useContributions(year: number, enabled = true) {
  return useQuery({
    queryKey: ["contributions", year],
    queryFn: () => apiFetch<ContributionResponse>(`/contributions/?year=${year}`),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useContributionStreak(year: number, enabled = true) {
  return useQuery({
    queryKey: ["contribution-streak", year],
    queryFn: () => apiFetch<ContributionStreak>(`/contributions/streak?year=${year}`),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useContributionStatistics(year: number, enabled = true) {
  return useQuery({
    queryKey: ["contribution-statistics", year],
    queryFn: () =>
      apiFetch<ContributionStatistics>(`/contributions/statistics?year=${year}`),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRefreshContributions(year: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ detail: string; data?: { year: number; connected: boolean } }>(
        "/contributions/refresh",
        { method: "POST", body: JSON.stringify({ year }), csrf: true },
      ),
    retry: false,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contributions"] });
      void queryClient.invalidateQueries({ queryKey: ["contribution-streak"] });
      void queryClient.invalidateQueries({ queryKey: ["contribution-statistics"] });
    },
  });
}
