# Java Agent experiment

Baseline: Aetherloom v0.3.0 / 6b2d5768b4d05e9618357d125a18e5c429783c38;
Bridge v0.1.0 / 58703f093407c8c34750313c86c5e828746c1a0b.

Single game JVM; application dependencies and helpers embedded in one EXE.
Use existing user Java only; agent matrix 8/11/17/21/25 does not override game Java requirements.
No production worlds or ECS deployment. Experimental branch only; stable release remains Latest.

Gate 1: a Java-8-bytecode agent must load on all five Java runtimes without
external dependencies, and must safely discover the actual game class loader.
Gate 2: mapped control adapter must prove automatic world/LAN/join/save/exit and
authenticated custom UUID before a configuration is allowed to commit cloud saves.
Gate 3: repeat handoff and fault tests before promoting any new environment.
Never advertise a diagnostic probe as a complete Hop adapter.

First attempt: discover the game loader with Instrumentation, then use explicit
Forge event signatures and version mappings instead of linking a Forge development
environment into the agent. If this cannot safely cover required capabilities,
record the concrete failure and return the active checkout/artifacts to baseline.
Unsupported combinations fail closed; manual mode never bypasses save/identity gates.

## First experiment results

- Real Minecraft 1.20.1 / Forge47.4.22, existing Java17: no Bridge Mod installed,
  selected world opened, LAN published, normal save and file-lock release, process exit passed.
- Local temporary authority/relay, two real game processes with test-only inventory
  fixture: Player automatic joining, custom UUID first save and second join with
  23 levels / 2 emeralds preserved, Player exit without upload, Host final commit passed.
- Fixed experimentally observed Windows agent-argument path encoding and Forge
  thread-context class-loader requirements. In-memory Host login is distinguished
  from authenticated remote players; unknown remote identities are rejected.
- Agent HTTP work runs outside the game main thread. An error latches the control
  session failed and prevents a later save event from being accepted as success.
- Windows/Linux Java8/11/17/21/25 CI tests check bootstrap only. Full-game matrix,
  20 handoffs per combination, fault/performance certification remain pending.
- No stable promotion: Agent remains explicitly opt-in. The original Bridge
  repository remains the fallback and has its own versioned source pin.
- The separate playerdata helper currently requires Java17. A compatible Agent
  alone does not make Java8/11 Minecraft environments eligible for full Hop.

## Rollback

v0.4.0a4 extends the Agent to Minecraft 1.21.1 / Forge52 (tested52.1.16,
Java21). Real offline and signed local Yggdrasil two-process tests passed
automatic LAN, repeat custom-UUID inventory/XP, Player no-upload and Host final
save/exit. Forge52 configuration tasks differ from older negotiation events;
offline client profiles must align after its earlier login packet. External
verified profiles are never rewritten. QuickPlay registration includes a
selected-world readiness recovery to handle already-started servers.

From v0.4.0a6 Agent room matching checks only the exact Minecraft version.
Loader type, Forge major/patch and the verified-combination allowlist are no
longer gates. The Agent entrypoint also accepts arbitrary adapter labels;
actual Forge event availability selects the configuration API path. Runtime
capability, identity and save barriers still fail closed. This implementation
uses Forge events; removing the gate does not implement Fabric/NeoForge support
or certify arbitrary Mod packs. Bridge fallback keeps its existing limits.
Personal launching has no such room restriction. Java bootstrap CI is still
distinct from full-game compatibility.

Stable dev and v0.3.0 remain at the baseline. Disable the experimental control
option and rebind, or replace the EXE with v0.3.0. Never overwrite an interrupted
world: resolve its pending recovery first. Do not reset shared branch history.
