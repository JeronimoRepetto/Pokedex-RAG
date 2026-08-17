# ADR-0005: LLM judge model — reuse `ai-studio-gemini`, don't add a third provider

- **Status:** accepted
- **Date:** 2026-08-06

## Context

Phase 5.5 needs an LLM judge for groundedness/hallucination verdicts, from a model
**different from the generator** — a model must not grade its own homework; a shared
failure mode (the same weights making the same mistake) would let a hallucination the
generator is confident about sail straight through undetected.

The generator (`LLM_PRIMARY`) is `vertex-gemini` (`gemini-3.6-flash`). Phase 4 already
stood up a second, fully independent provider — `ai-studio-gemini`
(`gemini-3.5-flash-lite`, ADR-0004) — with a different auth path (API key, not ADC)
and a different underlying serving stack (Gemini Developer API vs. Vertex AI). That
independence is exactly what "different from the generator" is asking for.

## Decision

`JUDGE_PROVIDER=ai-studio-gemini`. No third provider stood up for judging.
Enforced at startup (`main.py`): if `JUDGE_PROVIDER == LLM_PRIMARY`, `create_app`
raises `ValueError` before the app serves a single request — this is a fail-fast
config check, not a code-review reminder that can be forgotten.

The judge asks for a structured JSON verdict (`response_mime_type=application/json`)
rather than free-text parsing — `{"grounded": bool, "hallucination": bool, "reasoning": str}`.
A judge failure (provider error, unparseable JSON) fails **open** (assumed grounded,
warning logged) — the judge is a quality gate, not a correctness gate; a broken judge
must never take `/chat` down with it.

## Alternatives considered

- **A third, judge-only provider** (e.g. Ollama local, or a fresh AI Studio model
  variant) — genuinely more independent (zero shared infrastructure with either the
  generator or the fallback path), but adds a new provider, new credentials, and new
  failure surface for a Phase-5 milestone whose actual goal is the judge *logic*
  (verdict parsing, reformulate/abstain routing), not provider diversity. Revisit if
  `ai-studio-gemini` and `vertex-gemini` are ever observed sharing a correlated
  failure mode in practice — no evidence of that yet.
- **Same model, different prompt** ("critique your own answer") — rejected outright;
  this is the literal failure mode ADR-0005 exists to avoid, not a mitigation of it.
- **A rule-based / non-LLM judge** (e.g. only the deterministic `validate` node from
  5.4) — insufficient on its own: `validate` only catches type claims against a closed
  vocabulary; groundedness/hallucination need semantic judgment `validate`'s regex
  approach can't provide. The two are complementary, not substitutes — both run.

## Consequences

- Zero new infrastructure for 5.5 — `ai-studio-gemini` was already registered,
  live-verified, and budget-guarded (ADR-0004, devlog 0023). The fail-fast check
  means `JUDGE_PROVIDER=vertex-gemini` (a misconfiguration) is caught at startup, not
  discovered later as "the judge never seems to catch anything."
- If `LLM_PRIMARY` and `LLM_FALLBACK` are ever both AI-Studio-family models (unlikely
  given `LLM_FALLBACK=ai-studio-gemini` today, but worth remembering if that changes),
  re-check this decision — the independence argument depends on the judge NOT sharing
  a provider with whichever model actually answered a given request.
- Live-verified end-to-end (devlog 0030): real `vertex-gemini` generation + real
  `ai-studio-gemini` judgment in the same `/chat` request, correct verdict, no false
  rejection.
