import { apiFetch } from "@/api/client";
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

export interface AskAiInput {
  prompt: string;
  role: Role;
  permissions: Permission[];
}

export async function askAi({ prompt, role, permissions }: AskAiInput): Promise<AiMessage> {
  return apiFetch("/ai/ask", { method: "POST", body: { prompt } });
}