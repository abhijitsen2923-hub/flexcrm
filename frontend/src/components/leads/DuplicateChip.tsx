// Duplicate-lead indicator shown next to a lead's name in the list/kanban.
// A shared phone NUMBER resolves to "Fresh" (nobody owns it yet) or "Assigned"
// (already given to someone — the owner name is shown to managers/owner, withheld
// for reps so `owner` arrives null). Falls back to a plain "Duplicate" chip for an
// email-only match. Renders nothing for a non-duplicate lead.

interface DuplicateChipProps {
  status?: "fresh" | "assigned" | null;
  owner?: string | null;
  isDuplicate?: boolean;
}

export function DuplicateChip({ status, owner, isDuplicate }: DuplicateChipProps) {
  if (status === "assigned") {
    const label = owner ? `Assigned · ${owner}` : "Assigned already";
    const title = owner
      ? `This number is already assigned to ${owner}`
      : "This number is already assigned to another lead";
    return (
      <span className="dup-chip dup-chip--assigned" title={title} aria-label={title}>
        {label}
      </span>
    );
  }
  if (status === "fresh") {
    return (
      <span
        className="dup-chip dup-chip--fresh"
        title="Fresh — this number isn't assigned to anyone yet"
        aria-label="Fresh lead"
      >
        Fresh
      </span>
    );
  }
  if (isDuplicate) {
    return (
      <span
        className="dup-chip dup-chip--dup"
        title="Possible duplicate — shares an email or phone with another lead"
        aria-label="Possible duplicate lead"
      >
        Duplicate
      </span>
    );
  }
  return null;
}
