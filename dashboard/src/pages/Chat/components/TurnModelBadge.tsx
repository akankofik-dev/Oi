import { memo } from "react";
import { Cpu } from "lucide-react";

interface TurnModelBadgeProps {
  /** Resolved model ref, e.g. "pollinations/Atria-Dawn-Preview". */
  modelRef: string | null | undefined;
}

/**
 * Small, subtle badge showing which model is actually used for this turn.
 * Uses resolved_model from the backend (handles 'auto' mode correctly).
 * Returns null when unknown — silent is better than wrong.
 */
function TurnModelBadge({ modelRef }: TurnModelBadgeProps) {
  if (!modelRef) return null;

  const trimmed = modelRef.trim();
  if (!trimmed) return null;

  // Show short name: "Atria-Dawn-Preview" from "pollinations/Atria-Dawn-Preview".
  const shortName = trimmed.split("/").pop() || trimmed;

  return (
    <span className="turnModelBadge" title={`Model: ${trimmed}`}>
      <Cpu size={11} aria-hidden />
      <span className="turnModelBadgeText">{shortName}</span>
    </span>
  );
}

export default memo(TurnModelBadge);
