# ADR 0003: A deterministic offline "Replay" model

**Status:** accepted

## Context
The project must run for anyone, with no API keys, and tests must be deterministic. Mocking the LLM away
would also skip the most important code paths.

## Decision
`ReplayProvider` implements the same `LLMProvider` interface as Claude. Per agent role, a small script
reads the conversation and tool results and picks the next tool call, as a model would. It drives the
same LangGraph loop, tool registry, approval policy, Temporal workflows and channels. Token usage is
estimated and priced with real prices, and runs are labeled "simulated".

## Consequences
- Offline demos and tests exercise the real system end to end; switching `LLM_PROVIDER=anthropic`
  changes only the provider.
- The scripts encode plausible behavior, not reasoning; this is stated plainly in the README.
- Determinism (seeded per step and message count) makes golden tests and the backfilled history
  reproducible.
