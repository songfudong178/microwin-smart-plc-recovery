---
name: microwin-smart-plc-recovery
description: Write, modify, review, and repair Siemens S7-200 SMART PLC programs in MicroWIN SMART, including LAD-compatible AWL/STL generation, protected library integration, data-block preservation, and native offline acceptance. Use by default for this user's PLC programming tasks; apply Siemens-specific details only to MicroWIN SMART.
---

# MicroWIN SMART PLC Recovery

Use this skill when writing, modifying, reviewing, or recovering PLC programs for this user. Identify the PLC family and programming software first. The concrete import and LAD rules below apply to MicroWIN SMART; do not transfer Siemens opcodes, addresses, or import behavior to other vendors. Preserve approved control behavior and distinguish offline evidence from field state.

## Safety and scope

- Treat the `.smart` project, exported program blocks, data block, system block, symbols, and live PLC memory as distinct artifacts.
- Start read-only. Hash and preserve the original project and inspect the current candidate before changing anything.
- Do not infer permission to connect, download, change RUN/STOP, force values, clear memory, or bypass an emergency stop or other interlock.
- Before any non-trivial rewrite, explain the intended structural change, behavior impact, risks, rollback, tests, and acceptance criteria; obtain approval when required by the project.
- Keep actual site credentials, network details, PLC addresses, and process setpoints out of this reusable skill and user-facing summaries unless explicitly authorized and necessary.

## Before generating or editing PLC code

For this user's PLC names, comments, notes, point tables and explanations, read [references/plain-chinese.md](references/plain-chinese.md). Use concise plain Chinese grounded in the actual logic across all in-scope user POUs; preserve exact technical mappings and distinguish commands from confirmed device state. Updating text does not authorize changing logic or vendor libraries.

Read [references/programming-rules.md](references/programming-rules.md) before the first code edit. It is the primary prevention guide grounded in Siemens help, not an after-the-fact checklist. Establish the target CPU/software/library, address/type/ownership table, first-scan and retention behavior, scan order, legal Network forms, call signatures, and import scope before generating instructions. Reuse confirmed project evidence rather than asking the user for facts already available.

While writing, generate from known LAD structures and the actual library contracts. Reserve LB60-LB63 for the compiler's call wiring; do not use it as cross-Network user scratch. Choose numeric opcodes by declared type, allocate timer/edge state before reuse, and design each asynchronous Modbus request's full lifetime before writing its trigger. Keep final native verification as the last layer, not the primary way to discover these constraints.

For vendor-specific uncertainty, read the matching official topic listed in the guide before coding that part. Treat engineering preferences, actual native observations, and official guarantees as different evidence.

## Required checkpoints, not promises of first-pass success

Use these checkpoints for non-trivial PLC changes. Existing verified project facts may be reused, but never invent a completed check. A skill cannot guarantee first-pass compilation or safe field operation.

1. **Before writing:** record the approved scope, exact baseline hash, CPU/software/library identity, capacity basis, address/type/owner map, scan/retention contract and affected POU list. Identify missing evidence and block only the dependent work. Check CPU capacity early with the real libraries and representative native structure; line count is not compiled size. A CPU change requires separate approval.
2. **Before generation or symbol edits:** read [references/symbol-migration.md](references/symbol-migration.md) whenever names, tables, program imports or DB references change. Define native symbols separately from display labels; preserve I/O, system, POU and library tables. Establish the old-name/address/type/new-name mapping and all affected references before clearing any table.
3. **Before importing:** read [references/preflight-tool.md](references/preflight-tool.md), prepare the bounded input manifest, and run `scripts/plc_preflight.py` for generated AWL/symbol/DB payloads. Use its companion tests when changing the checker. Resolve errors; explicit review findings require evidence, not a flag set merely to silence them. This script is not a Siemens compiler. Re-run the same generators from unchanged inputs into a separate directory and compare outputs; do not execute unknown build commands from a manifest.
4. **Before native integration:** read [references/native-integration.md](references/native-integration.md). Verify the operation in a separate candidate, including whether the selection is text, an operand, a Network or a POU. Do not assume paste replaces selected program segments or that changing a symbol display mode repairs bindings. After one failed edit, preserve the observed error and check the documented mechanism before trying again; after two failed attempts with the same mechanism, stop that approach.
5. **Before handoff:** follow the evidence gates in `native-integration.md`. Each result must name the input/candidate hashes and software/CPU identity. Source, symbols, DB, system settings or library changes invalidate dependent results. Passing a subset cannot upgrade unchecked compile/LAD/save-reopen/field status.

Keep this skill Siemens-specific. For another vendor or language, use that platform's official documentation and tooling; do not transplant these opcodes, memory layouts or import rules. `ST40` is a CPU model, not permission to switch to IEC Structured Text. Respect an explicitly requested language, after checking platform support.

## Author LAD-compatible code from the start

- When diagnosing conversion failures or handling a prior invalid deliverable, read [references/lad-authoring.md](references/lad-authoring.md) for the failure record and native acceptance method. Use the programming rules above during ordinary authoring.
- Default to an editable native LAD deliverable for this user. An AWL review file or a successful compile alone is not a completed ladder deliverable.
- Use one independent logical rung per Network unless the native editor has demonstrated the exact multi-output/branch structure. Repeated `LD` is a review signal, not a safe automatic splitting rule: nested `ALD`/`OLD`, branch stacks, and compiler-generated BOOL call wiring require separate analysis.
- Verify one representative structure in an isolated native project before applying it to all similar networks. Keep an old-to-new Network map when splitting.

## Diagnose before rewriting

1. Establish which artifact was imported or downloaded and which download options were selected.
2. Separate these symptom classes:
   - values became zero or reverted;
   - Chinese comments became garbled;
   - a program compiles but one or more Networks show `无效程序段` in LAD;
   - import or data-block import is disabled;
   - logic behavior changed after a structural conversion.
   - undefined symbols after table changes, or operand text appended rather than replaced.
   Record error code separately from error count, plus block/Network/line and the last edit. Do not rewrite algorithm logic to treat an integration error.
3. Read the relevant section of [references/failure-patterns.md](references/failure-patterns.md). For a conversion or recovery change, also use its acceptance checklist.
4. Inspect every affected Network and at least scan the remaining Networks in the same POU. A successful first Network does not prove later Networks are convertible.

## Change discipline

- Prefer the smallest transformation that MicroWIN itself can render as LAD.
- Preserve comparison operators, operands, constants, coil types, timer presets, execution order, and call position unless the user separately approves a behavior change.
- For complex Networks, test one representative small rewrite in an isolated project before applying the pattern broadly.
- If branch-based conversion fails twice, stop increasing or merely rearranging branch counts. Reassess function-box height, logic-stack shape, and whether helper subroutines or additional Networks are required.
- When moving logic to a helper subroutine, keep its call at the original scan position and verify that no intervening logic changes the order.
- Generate import files separately from the original `.smart` file. Never overwrite the only rollback copy.
- Keep native symbol formatting in the generator, not in a one-off pasted table. Test regeneration and native round-trip separately.

## Evidence and handoff

- Distinguish static checks, successful AWL import, LAD display, full compile, save/reopen verification, and live PLC/field acceptance. None substitutes for the next stage.
- Report exactly which Networks were visually confirmed and which remain unchecked.
- Never describe an unknown cause as resolved just because a new window compiled; keep failure history and bind subsequent evidence to the exact saved artifact.
- Do not call the result production-ready until all affected Networks render normally, full compile reports zero errors and zero warnings, the data block is verified, and authorized field validation is complete.
