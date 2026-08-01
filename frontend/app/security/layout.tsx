import { DashboardShell } from "@/components/dashboard/shell";

export default function SecurityLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
