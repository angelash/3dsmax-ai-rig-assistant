# Stage01 CT-Guided Biped Rigging

Use this workflow when refining Stage01 Biped candidates for the A1 character set. This is an agent-controlled rigging procedure, not a blind batch script. Scripts are tools for measurement, visualization, and mechanical edits; the agent owns the order of operations, acceptance decisions, retries, and questions.

This skill is governed by `docs/stage01-self-learning-rigging-standard.md`. When a rigging task starts, apply that standard by default: deliver the best current asset output and also record tool gaps, failed attempts, and next tool improvements.

## Core Rule

Guide points only create the initial Biped. After the initial Biped exists, do not chase Guide points as proof of correctness. Refine and accept the Biped by CT-style cross sections, multiview wire/bone views, and local anatomy/garment reasoning.

## Control Loop

For every editable bone segment:

1. Inspect current evidence.
2. Adjust only the active node/segment and its local child length/orientation.
3. Regenerate or sample CT slices for that segment.
4. Accept only if the bone center is wrapped in the local point-cloud section and the multiview line still follows the intended anatomy.
5. Lock the accepted parent/segment before moving down the chain.
6. If a change improves one slice but breaks an already locked section, revert or reduce it.
7. If repeated attempts do not reduce failures, increase evidence first: denser stations, thicker/slightly shifted slabs, side/top crops, textured view, or reference answer comparison.
8. If added evidence still leaves ambiguity, record the question and stop pretending the segment is solved.

## Required Order

Work from stable anchors to dependent chains. Do not globally iterate the whole Biped unless the workflow explicitly says the current locked state can be invalidated.

1. `Root / COM / Pelvis`
   - Establish ground, body center, pelvis height, and COM policy.
   - Validate pelvis and pelvis-to-spine sections before touching limbs.

2. `Body Center Chain`
   - Spine, chest, neck, head.
   - Resolve head versus crest/helmet/hair. HeadTop/CrestTop are visual references unless the rig intentionally extends structure.

3. `Lower Body`
   - Pelvis to left/right hip.
   - Hip to knee.
   - Knee to ankle.
   - Ankle to toe/foot pivot.
   - Validate left and right separately; mirrored appearance is not proof under skirts, robes, boots, or asymmetric armor.

4. `Upper Body`
   - Chest to clavicle.
   - Clavicle to shoulder.
   - Shoulder to elbow.
   - Elbow to wrist.
   - Wrist to hand mass.
   - Watch for sleeve volume; the centerline should follow the arm/hand mass, not the outer cloth edge.

5. `Deferred Details`
   - Fingers, weapons, cloth, crest, hair, ornaments, wings, tails, and props are not allowed to pull the main Biped chain away from the body.
   - Record them for later structure or Skin work.

## Acceptance Criteria

A segment is accepted only when all relevant checks pass:

- CT slice stations are green for the active segment.
- The accepted parent remains green.
- Front/side/top wire/bone views agree with the local anatomy.
- The Biped node position and segment length are plausible relative to the reference answer or visible body mass.
- No previously locked section regresses.

## Evidence Escalation

When CT slices fail or the evidence is thin:

- Increase station density near the failed area, especially around joints.
- Add offset slices around the joint, not only exact 0/25/50/75/100% stations.
- Increase slab thickness only if the section has too few points; reject the change if it hides a real miss.
- Compare front, side, and top wire/bone views.
- Use textured views to identify cloth, armor, hair, or prop volumes that should not drive the skeleton.
- Compare against the AccuRig reference answer when available.

Keep changes only when they reduce strict failures without increasing accepted-section failures or producing worse multiview alignment.

## Stop Conditions

Stop and report instead of forcing a fake pass when:

- Strict CT failures do not decrease after evidence escalation and conservative local edits.
- A Biped structural constraint prevents the required node/length/orientation change.
- The point cloud does not expose the hidden anatomy well enough to decide.
- The visible mesh is cloth/armor only and the underlying joint cannot be inferred confidently.
- Reference answer comparison conflicts with mesh evidence and needs an MDC decision.

The report must list the unresolved segment, failed stations, attempted fixes, evidence added, whether each attempt was positive or negative, and the exact question to ask.

## Tooling Contract

Scripts may:

- Generate initial Guide points.
- Create and edit Biped nodes mechanically.
- Generate CT slices, wire/bone views, crops, and status tables.
- Apply local adjustments requested by the agent.

Scripts must not:

- Treat iteration count as success.
- Mark a failed CT segment as ready.
- Override locked accepted sections without an explicit agent decision.
- Decide that a semantically ambiguous cloth/armor shape is the true limb center.

## Practical Review Notes

- A red CT slice is not a cosmetic issue; it blocks Stage01 handoff.
- Internal Max refinement metrics are diagnostic only. The strict Python CT slice gate is the handoff blocker.
- The right answer in research phase is often a clear blocker report, not another blind iteration.
- Each run must leave a learning trail: what improved, what regressed, what should become a tool, and what question still needs MDC/reference confirmation.
