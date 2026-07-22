import type {
  ActivityType,
  CustomerStatus,
  DealStage,
  DealStatus,
  LeadIndustry,
  PipelineStageCategory,
  TaskPriority,
  TaskStatus,
  UserRole,
  UserStatus
} from "../types";


type Option<T extends string> = { value: T; label: string };


function asOptions<T extends string>(values: ReadonlyArray<T>, labelFn?: (v: T) => string): Option<T>[] {
  return values.map((value) => ({
    value,
    label: labelFn ? labelFn(value) : titleCase(value)
  }));
}


function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}


export const customerStatusOptions: Option<CustomerStatus>[] = asOptions([
  "prospect",
  "active",
  "inactive",
  "churned"
]);

export const leadIndustryOptions: Option<LeadIndustry>[] = asOptions([
  "education",
  "travel",
  "real_estate"
]);

// Controlled lead-source list — prevents free-text fragmentation and keeps values
// aligned with historical / CSV data. "Other" reveals a free-text field.
export const leadSourceOptions: Option<string>[] = [
  "Walk-in", "Reference", "Instagram", "Facebook / Meta", "WhatsApp",
  "Google Ads", "Website", "99acres", "MagicBricks", "Housing.com",
  "Cold call", "Newspaper / Print", "Hoarding", "Other"
].map((v) => ({ value: v, label: v }));

// Real-estate "Property Interest" (unit configuration). "Other" → free text.
export const propertyInterestOptions: Option<string>[] = [
  "1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK+", "Studio", "Penthouse",
  "Duplex", "Plot / Land", "Villa", "Commercial", "Other"
].map((v) => ({ value: v, label: v }));

// Real-estate property TYPE (value-keyed; label differs). "Other" → free text.
export const propertyTypeOptions: Option<string>[] = [
  { value: "apartment", label: "Apartment" },
  { value: "villa", label: "Villa / Independent house" },
  { value: "plot", label: "Plot / Land" },
  { value: "commercial", label: "Commercial" },
  { value: "Other", label: "Other…" },
];

// Contact salutation for the New Lead form.
export const salutationOptions: Option<string>[] = ["Mr", "Mrs", "Ms", "Master"].map((v) => ({ value: v, label: v }));

// Sentinel that triggers the "please specify" free-text input.
export const OTHER_OPTION = "Other";

export const dealStageOptions: Option<DealStage>[] = asOptions([
  "discovery",
  "proposal",
  "negotiation",
  "closed_won",
  "closed_lost"
]);

export const dealStatusOptions: Option<DealStatus>[] = asOptions([
  "open",
  "won",
  "lost",
  "on_hold"
]);

export const taskPriorityOptions: Option<TaskPriority>[] = asOptions([
  "low",
  "medium",
  "high",
  "urgent"
]);

export const taskStatusOptions: Option<TaskStatus>[] = asOptions([
  "pending",
  "in_progress",
  "completed",
  "cancelled"
]);

export const activityTypeOptions: Option<ActivityType>[] = asOptions([
  "note",
  "call",
  "email",
  "meeting",
  "task",
  "status_change"
]);

export const userRoleOptions: Option<UserRole>[] = asOptions([
  "admin",
  "manager",
  "sales",
  "support",
  "analyst"
]);

export const userStatusOptions: Option<UserStatus>[] = asOptions([
  "active",
  "inactive",
  "invited",
  "suspended"
]);


type StatusTone = "neutral" | "primary" | "success" | "warning" | "danger" | "info";


export function customerStatusTone(status: CustomerStatus): StatusTone {
  return status === "active"
    ? "success"
    : status === "prospect"
      ? "info"
      : status === "churned"
        ? "danger"
        : "neutral";
}

export function pipelineCategoryTone(category: PipelineStageCategory): StatusTone {
  if (category === "closed_won") return "success";
  if (category === "closed_lost") return "danger";
  return "warning";
}

export function dealStageTone(stage: DealStage): StatusTone {
  return stage === "closed_won"
    ? "success"
    : stage === "closed_lost"
      ? "danger"
      : stage === "negotiation" || stage === "proposal"
        ? "warning"
        : "info";
}

export function dealStatusTone(status: DealStatus): StatusTone {
  return status === "won"
    ? "success"
    : status === "lost"
      ? "danger"
      : status === "on_hold"
        ? "warning"
        : "info";
}

export function taskPriorityTone(priority: TaskPriority): StatusTone {
  return priority === "urgent" || priority === "high"
    ? "danger"
    : priority === "medium"
      ? "warning"
      : "neutral";
}

export function taskStatusTone(status: TaskStatus): StatusTone {
  return status === "completed"
    ? "success"
    : status === "in_progress"
      ? "info"
      : status === "cancelled"
        ? "neutral"
        : "warning";
}


export function industryInterestLabel(industry: LeadIndustry): string {
  return industry === "travel"
    ? "Destination"
    : industry === "real_estate"
      ? "Property Interest"
      : "Course";
}


export { titleCase };
