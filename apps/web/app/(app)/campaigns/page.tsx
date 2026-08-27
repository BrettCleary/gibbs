"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import type { CampaignCreate } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { problemInfo } from "@/lib/problems";
import { CampaignForm } from "@/components/CampaignForm";
import {
  Button,
  DataValue,
  EmptyState,
  LoadingNote,
  PageTitle,
  ProgressBar,
  StatusBadge,
  Surface,
  Table,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui/primitives";

export default function CampaignsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns");
      return data ?? [];
    },
    refetchInterval: 5000,
  });

  const create = useMutation({
    mutationFn: async (body: CampaignCreate) => {
      const { data, error } = await api.POST("/campaigns", { body });
      if (error) throw error;
      return data!;
    },
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      router.push(`/campaigns/${campaign.id}`);
    },
  });

  const list = campaigns.data ?? [];
  const nRunning = list.filter((c) => c.status === "RUNNING").length;

  return (
    <div className="flex flex-col gap-8">
      <PageTitle
        eyebrow="Mission control"
        title="Discovery campaigns"
        description="Each campaign hands the autonomous scientist an objective and a finite simulation budget. It forms hypotheses, chooses calculations, diagnoses failures, updates its models, and explains what it found."
        actions={
          !showForm && (
            <Button
              variant="primary"
              icon={<Plus className="h-3.5 w-3.5" />}
              onClick={() => setShowForm(true)}
            >
              New campaign
            </Button>
          )
        }
      />

      {showForm && (
        <CampaignForm
          onSubmit={(body) => create.mutate(body)}
          onCancel={() => setShowForm(false)}
          pending={create.isPending}
          error={
            create.error
              ? String((create.error as { detail?: unknown })?.detail ?? create.error)
              : null
          }
        />
      )}

      <Surface>
        {campaigns.isLoading ? (
          <LoadingNote>Loading campaigns</LoadingNote>
        ) : campaigns.isError ? (
          <EmptyState
            title="API unreachable"
            description="The web app could not reach the AlloyLab API. Start it with `pnpm --filter @alloylab/api dev` and this list will populate."
          />
        ) : list.length === 0 ? (
          <EmptyState
            title="No campaigns yet"
            description="Create one to launch the autonomous scientist. The default problem searches for the stiffest Ni–Al ordering that is thermodynamically stable and stays ordered at 1200 K."
            action={
              <Button
                variant="primary"
                icon={<Plus className="h-3.5 w-3.5" />}
                onClick={() => setShowForm(true)}
              >
                New campaign
              </Button>
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Campaign</Th>
                <Th>Problem</Th>
                <Th>Strategy</Th>
                <Th>Status</Th>
                <Th className="w-48">Budget</Th>
                <Th className="hidden lg:table-cell">Objective</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => {
                const info = problemInfo(c.problem_type);
                return (
                  <Tr key={c.id} clickable onClick={() => router.push(`/campaigns/${c.id}`)}>
                    <Td className="py-3">
                      <div className="font-medium text-text">{c.name}</div>
                      <div className="mt-0.5 font-mono text-[10px] text-text-muted">
                        {c.id.slice(0, 8)}
                      </div>
                    </Td>
                    <Td>
                      <Tag>{info.milestone}</Tag>
                    </Td>
                    <Td>
                      <DataValue className="text-[12px]">{c.strategy}</DataValue>
                    </Td>
                    <Td>
                      <StatusBadge status={c.status} />
                    </Td>
                    <Td>
                      <div className="flex items-center gap-3">
                        <ProgressBar
                          value={c.simulations_used}
                          max={c.simulation_budget}
                          tone={c.status === "COMPLETED" ? "good" : "accent"}
                          className="w-20"
                        />
                        <DataValue className="text-[12px]">
                          {c.simulations_used}
                          <span className="text-text-muted"> / {c.simulation_budget}</span>
                        </DataValue>
                      </div>
                    </Td>
                    <Td className="hidden max-w-md truncate text-[12.5px] text-text-secondary lg:table-cell">
                      {c.objective}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
        {list.length > 0 && (
          <div className="flex items-center gap-4 border-t border-line px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
            <span>{list.length} campaigns</span>
            {nRunning > 0 && <span className="text-accent-bright">{nRunning} running</span>}
          </div>
        )}
      </Surface>
    </div>
  );
}
