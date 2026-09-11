import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import type { Permission, Role } from "@/types";

export interface AiTool {
  id: string;
  label: string;
  description: string;
  permission: Permission;
  prompt: string;
}

export const AI_TOOLS: AiTool[] = [
  {
    id: "lesson_plan",
    label: "Draft a lesson plan",
    description: "Full lesson plan for a topic you teach",
    permission: "ai.teaching",
    prompt: "Draft a 45-minute lesson plan on simple equations for JSS 2.",
  },
  {
    id: "quiz",
    label: "Generate a quiz",
    description: "10 questions with an answer key",
    permission: "ai.teaching",
    prompt: "Generate a 10-question quiz on photosynthesis for Primary 6.",
  },
  {
    id: "class_performance",
    label: "Analyse my class",
    description: "Performance summary for classes assigned to you",
    permission: "ai.teaching",
    prompt: "Summarise how JSS 2A performed in Mathematics this term.",
  },
  {
    id: "school_performance",
    label: "School performance analysis",
    description: "Cross-class academic insight",
    permission: "ai.academic",
    prompt: "Which classes are underperforming this term and why?",
  },
  {
    id: "attendance_insight",
    label: "Attendance insight",
    description: "Attendance trends and students at risk",
    permission: "ai.academic",
    prompt: "Which students are at risk from low attendance?",
  },
  {
    id: "fee_summary",
    label: "Fee collection summary",
    description: "Collections, outstanding balances, trends",
    permission: "ai.finance",
    prompt: "Summarise this term's fee collection and outstanding balances.",
  },
  {
    id: "child_performance",
    label: "Explain my child's results",
    description: "Plain-language explanation of the report card",
    permission: "ai.parent",
    prompt: "Explain Ahmed's first term results in simple language.",
  },
  {
    id: "study_help",
    label: "Explain a topic to me",
    description: "Study help on your subjects",
    permission: "ai.student",
    prompt: "Explain the water cycle in simple terms.",
  },
  {
    id: "platform_health",
    label: "Platform health digest",
    description: "Tenant, revenue and reliability digest",
    permission: "ai.platform",
    prompt: "Summarise platform health and churn risk this month.",
  },
];

export interface AiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  denied?: boolean;
  creditsUsed?: number;
}

const DENIED_TOPICS: Record<string, Permission> = {
  fee: "ai.finance",
  fees: "ai.finance",
  payment: "ai.finance",
  salary: "ai.finance",
  payroll: "ai.finance",
  revenue: "ai.finance",
  subscription: "ai.finance",
};

export interface AskAiInput {
  prompt: string;
  role: Role;
  permissions: Permission[];
}

export async function askAi({ prompt, role, permissions }: AskAiInput): Promise<AiMessage> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/ai/ask", { method: "POST", body: { prompt } });

  const lowered = prompt.toLowerCase();
  const restricted = Object.entries(DENIED_TOPICS).find(([word]) => lowered.includes(word));
  if (restricted && !permissions.includes(restricted[1])) {
    return mockDelay(
      {
        id: `ai_${Date.now()}`,
        role: "assistant",
        denied: true,
        content:
          "I can't help with that. Financial information is outside the data your role is authorised to access. Your school administrator or bursar can share it if needed.",
      },
      700,
    );
  }

  const answer =
    role === "parent"
      ? "Ahmed scored an average of 72% this term. He is strongest in Mathematics (81%) and needs support in Basic Science (58%). His attendance is 92%, which is good. Practising two Basic Science exercises each week should help before the next term."
      : role === "teacher"
        ? "JSS 2A averaged 64% in Mathematics. 8 of 34 students scored below 40% — mostly on word problems involving equations. Suggested next step: a 15-minute revision drill on translating word problems, then a short 5-question diagnostic."
        : role === "accountant"
          ? "First term invoices total ₦18.4m. ₦14.2m collected (77%), ₦4.2m outstanding across 96 students. Cash collections are 41% of the total; bank transfers 38%. 6 transfers are awaiting verification."
          : role === "platform_manager"
            ? "42 tenants: 31 active, 4 trial, 3 pending payment, 2 suspended, 2 in grace. MRR is ₦1.06m, up 6% month-on-month. Two schools crossed their student growth allowance and should be prompted to upgrade."
            : "Across the school, average performance is 68%. JSS 3 and SS 1 are trending down in Mathematics, while Primary 4–6 improved by 5 points. 18 students have attendance below 70% and 23 result sheets are awaiting approval.";

  return mockDelay(
    { id: `ai_${Date.now()}`, role: "assistant", content: answer, creditsUsed: 3 },
    1100,
  );
}
