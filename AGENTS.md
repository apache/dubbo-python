# Guidance for coding agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) first: its setup, checks, code
conventions and test rules apply to every change. This file adds what an
agent needs beyond them.

## Product boundary

- This repository is a Python-native RPC framework for the Apache Dubbo
  ecosystem. It owns the end-to-end Python experience of defining, exposing,
  discovering and invoking Dubbo services.
- Interoperable formats, observable behavior, shared Dubbo roles and
  vocabulary, and public extension contracts belong to the cross-language
  Dubbo model; keep each at the fidelity its consumers need, and let Python
  own the SDK mechanics.
- Treat Dubbo Java and Go as related implementations, not independent
  specifications. Split an upstream construct into its shared commitment and
  its language-specific mechanism before reusing its structure, and compare
  references only at the same actor, capability and layer.
- Treat adoption and mainstream practice as evidence about tradeoffs, not as
  authority; check the underlying constraint and how it fits this project.

## Working rules

- Read the affected implementation, its callers, tests, exports and
  configuration before editing.
- Establish the requested outcome and its non-goals before adding files or
  abstractions.
- Stop and ask before any change that CONTRIBUTING.md says to discuss first:
  public API, package boundaries, protocol or serialization behavior,
  dependencies, tooling or layout.
- Run the checks of CONTRIBUTING.md on what you touch, and report exactly
  which ran and their results. Never claim that a check passed without
  running it.
- Keep generated output, local environments, editor state, reports and
  personal instructions out of version control.
