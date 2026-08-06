"""Per-run markdown report generator (Phase 6.4).

Langfuse is the live dashboard; these reports are the portfolio artifact — a committed,
diffable snapshot of what one evaluation run actually measured, including the operational
numbers (latency percentiles, tokens, cost per answer) that quality metrics alone miss.

Cost is computed from a configured price table. A model with no configured price is
reported as unknown rather than guessed: a wrong number in a committed report is worse
than an honest gap (see the project's cost-log discipline).
"""

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from pokedex_db.models import EvalResult, EvalRun, RagAnswer


class ReportError(RuntimeError):
    """The requested run does not exist, or pricing configuration is unusable."""


def percentile(values: list[float], fraction: float) -> float:
    """Linear-interpolated percentile on a copy of `values`.

    `fraction` is 0..1 (0.5 = median). Chosen over `statistics.quantiles` because that
    one needs at least 2 data points and a single-case run is a legitimate report.
    """
    if not values:
        raise ValueError("percentile of an empty sequence is undefined")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction must be within 0..1, got {fraction}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float

    def cost(self, prompt_tokens: int, output_tokens: int) -> float:
        return (prompt_tokens * self.input_per_1m + output_tokens * self.output_per_1m) / 1_000_000


def parse_pricing(raw: str) -> dict[str, ModelPrice]:
    """`{"model-name": {"input_per_1m": 0.3, "output_per_1m": 2.5}, ...}` from config.

    Prices belong in configuration, never inline in code: they change without warning
    and a stale constant silently falsifies every future report.
    """
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReportError(f"MODEL_PRICING_JSON is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReportError("MODEL_PRICING_JSON must be an object keyed by model name")
    prices: dict[str, ModelPrice] = {}
    for model, entry in payload.items():
        try:
            prices[model] = ModelPrice(
                input_per_1m=float(entry["input_per_1m"]),
                output_per_1m=float(entry["output_per_1m"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReportError(
                f"pricing entry for {model!r} needs numeric input_per_1m and "
                f"output_per_1m; got {entry!r}"
            ) from exc
    return prices


@dataclass(frozen=True)
class AnswerStats:
    """Operational stats mined from the rag_answers rows written during the run."""

    answers: int = 0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0
    models: tuple[str, ...] = ()
    cost_usd: float | None = None
    unpriced_models: tuple[str, ...] = ()

    @property
    def cost_per_answer_usd(self) -> float | None:
        if self.cost_usd is None or not self.answers:
            return None
        return self.cost_usd / self.answers


def summarize_answers(rows: list[RagAnswer], prices: dict[str, ModelPrice]) -> AnswerStats:
    if not rows:
        return AnswerStats()
    latencies = [float(r.latency_ms) for r in rows if r.latency_ms is not None]
    models = sorted({r.model for r in rows if r.model})
    unpriced = tuple(m for m in models if m not in prices)
    known_cost = sum(
        prices[r.model].cost(r.prompt_tokens or 0, r.output_tokens or 0)
        for r in rows
        if r.model in prices
    )
    return AnswerStats(
        answers=len(rows),
        latency_p50_ms=percentile(latencies, 0.5) if latencies else None,
        latency_p95_ms=percentile(latencies, 0.95) if latencies else None,
        prompt_tokens=sum(r.prompt_tokens or 0 for r in rows),
        output_tokens=sum(r.output_tokens or 0 for r in rows),
        models=tuple(models),
        # All models unpriced -> no credible total at all, so report None, not 0.0.
        cost_usd=None if len(unpriced) == len(models) and models else known_cost,
        unpriced_models=unpriced,
    )


def load_run(session, run_id: int | None, suite: str | None) -> EvalRun:
    query = select(EvalRun).order_by(EvalRun.id.desc())
    if run_id is not None:
        run = session.get(EvalRun, run_id)
        if run is None:
            raise ReportError(f"no eval_runs row with id={run_id}")
        return run
    if suite:
        query = query.where(EvalRun.suite == suite)
    run = session.scalars(query.limit(1)).first()
    if run is None:
        raise ReportError(
            f"no eval runs found{f' for suite {suite!r}' if suite else ''} — run `evals run` first"
        )
    return run


def load_answers(session, run: EvalRun) -> list[RagAnswer]:
    """rag_answers has no FK to eval_runs (the API and the runner never talk), so the
    run's own time window is the join: every answer produced while it was running."""
    if run.finished_at is None:
        return []
    return list(
        session.scalars(
            select(RagAnswer)
            .where(RagAnswer.created_at >= run.started_at, RagAnswer.created_at <= run.finished_at)
            .order_by(RagAnswer.id)
        )
    )


def _fmt(value, spec: str = ".3f", fallback: str = "n/a") -> str:
    return fallback if value is None else format(value, spec)


def render_report(
    run: EvalRun,
    results: list[EvalResult],
    stats: AnswerStats,
    *,
    git_sha: str = "unknown",
    generated_at: datetime | None = None,
) -> str:
    duration = (
        f"{(run.finished_at - run.started_at).total_seconds():.1f}s" if run.finished_at else "n/a"
    )
    summary = dict(run.summary or {})
    provider = summary.pop("provider", None)
    space = summary.pop("space", None)
    lines = [
        f"# Eval run {run.id} — {run.suite}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Run id | {run.id} |",
        f"| Suite | {run.suite} |",
        f"| Cases | {run.case_count} |",
        f"| Started | {run.started_at.isoformat()} |",
        f"| Duration | {duration} |",
        f"| API | {run.api_base_url} |",
        f"| Git SHA | {git_sha} |",
    ]
    if provider:
        lines.append(f"| Provider | {provider} |")
    if space:
        lines.append(f"| Embedding space | {space} |")
    if generated_at is not None:
        lines.append(f"| Report generated | {generated_at.isoformat()} |")

    lines += ["", "## Quality metrics", "", "| Metric | Value |", "|---|---|"]
    for name, value in sorted(summary.items()):
        rendered = _fmt(value) if isinstance(value, (int, float)) else str(value)
        lines.append(f"| {name} | {rendered} |")

    lines += [
        "",
        "## Operational",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Answers recorded | {stats.answers} |",
        f"| Latency p50 | {_fmt(stats.latency_p50_ms, '.0f')} ms |",
        f"| Latency p95 | {_fmt(stats.latency_p95_ms, '.0f')} ms |",
        f"| Prompt tokens | {stats.prompt_tokens} |",
        f"| Output tokens | {stats.output_tokens} |",
        f"| Models | {', '.join(stats.models) or 'n/a'} |",
        f"| Total cost | {_fmt(stats.cost_usd, '.6f')} USD |",
        f"| Cost per answer | {_fmt(stats.cost_per_answer_usd, '.6f')} USD |",
    ]
    if stats.unpriced_models:
        lines += [
            "",
            f"> Cost excludes {', '.join(stats.unpriced_models)}: no price configured for "
            "these models. Add them to `MODEL_PRICING_JSON` rather than estimating by hand.",
        ]
    if stats.answers == 0:
        lines += [
            "",
            "> No `rag_answers` rows fall inside this run's window — expected for a "
            "retrieval-only suite, which never calls a generator.",
        ]

    failures = [
        r for r in results if isinstance(r.metrics, dict) and r.metrics.get("passed") == 0.0
    ]
    if failures:
        lines += ["", "## Failed cases", "", "| Case | Metrics |", "|---|---|"]
        lines += [
            f"| {r.case_id} | "
            + ", ".join(f"{k}={v}" for k, v in sorted(r.metrics.items()) if k != "passed")
            + " |"
            for r in failures
        ]

    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "cd apps/evals",
        f"poetry run evals run --suite {run.suite} --api-url {run.api_base_url}",
        f"poetry run evals report --run-id {run.id}",
        "```",
        "",
    ]
    return "\n".join(lines)
