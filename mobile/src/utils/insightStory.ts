import type { CurrentInsights, ReviewFinding } from "../types";

export type StoryTone = "calm" | "attention" | "positive";

export interface StoryBeat {
  id: string;
  chapter: string;
  title: string;
  body: string;
  tone: StoryTone;
  evidence: string[];
  confidence?: string;
}

export interface InsightStory {
  dateLabel: string;
  reviewWindow: { start: string | null; end: string | null; count: number };
  opening: string;
  coverage: { tracked: number; partial: number; unknown: number; total: number };
  goalCount: number;
  beats: StoryBeat[];
  questions: string[];
}

const sentence = (text: string) => text.split(/(?<=[.!?])\s+/)[0]?.trim() || text;

/**
 * Insight source paths are private implementation details.  The mobile app
 * receives them only as review citations, so it derives a date for review
 * context without exposing a path or attempting to read the memo itself.
 */
export function memoDateFromSourcePath(path: string): string | null {
  const match = path.match(/(?:^|\/)(\d{4}-\d{2}-\d{2})-[^/]+\.md$/);
  return match?.[1] ?? null;
}

function reviewWindow(sourceFiles: string[]): InsightStory["reviewWindow"] {
  const dates = sourceFiles.map(memoDateFromSourcePath).filter((date): date is string => Boolean(date)).sort();
  return { start: dates[0] ?? null, end: dates.at(-1) ?? null, count: sourceFiles.length };
}

function findingBeat(chapter: string, finding: ReviewFinding, tone: StoryTone, index: number): StoryBeat {
  return {
    id: `${chapter}-${index}-${finding.statement}`,
    chapter,
    title: chapter === "Momentum" ? "A signal worth keeping" : "A signal to notice",
    body: finding.statement,
    tone,
    evidence: finding.evidence_paths,
    confidence: finding.confidence,
  };
}

export function buildInsightStory(review: CurrentInsights): InsightStory {
  const { routine_review: routine, goal_review: goals, future_plan_review: future, life_pillar_review: pillars } = review.inference_bundle;
  const topics = pillars.groups.flatMap((group) => group.topics);
  const coverage = topics.reduce(
    (total, topic) => {
      if (topic.status === "tracked") total.tracked += 1;
      else if (topic.status === "partially_tracked") total.partial += 1;
      else total.unknown += 1;
      total.total += 1;
      return total;
    },
    { tracked: 0, partial: 0, unknown: 0, total: 0 },
  );
  const beats: StoryBeat[] = [
    ...routine.worked.map((item, index) => findingBeat("Momentum", item, "positive", index)),
    ...routine.did_not_work.map((item, index) => findingBeat("Friction", item, "attention", index)),
    ...future.progress_updates.map((item, index) => findingBeat("On the horizon", item, "calm", index)),
    ...future.new_additions.map((item, index) => findingBeat("A new thread", item, "calm", index)),
    // At-risk goals have their own persistent lane in the screen. Keeping
    // them out of the general story avoids both hiding and duplicate signals.
    ...goals.assessments.filter((goal) => goal.status !== "at_risk").map((goal, index) => ({
      id: `goal-${goal.id ?? goal.priority_key ?? index}`,
      chapter: "Direction",
      title: `${goal.id ?? goal.priority_key ?? "Goal"} · ${goal.status.replaceAll("_", " ")}`,
      body: goal.findings.length
        ? goal.findings.map((finding) => finding.statement).join(" ")
        : `Status: ${goal.status.replaceAll("_", " ")}. No additional finding was saved for this goal.`,
      tone: goal.status === "at_risk" ? "attention" : "calm" as StoryTone,
      evidence: goal.evidence_paths,
      confidence: goal.confidence,
    })),
  ];
  return {
    dateLabel: new Date(review.generated_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }),
    reviewWindow: reviewWindow(review.source_files),
    opening: sentence(review.narrative), coverage, goalCount: goals.assessments.length, beats,
    questions: future.unresolved_questions,
  };
}
