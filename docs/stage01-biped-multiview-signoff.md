# Stage01 Biped Multiview Signoff

Stage01 output is only a Biped candidate until front, side and top wrapping are signed off. Fast generation is useful only if the gate refuses bad candidates.

## Hard Gates

- Only `AIRA_Biped_COM` / Biped nodes may be used for the body skeleton. `AIRA_BONE_*` template bones are prohibited.
- Biped COM / Root must sit at the visual pelvis / body center, not at the floor.
- Front, side and top wire-bone views must all be reviewed before Skin setup.
- `frontWrap`, `sideWrap`, `topWrap`, `rootPelvisPolicy`, `crossSectionInsideVolume`, left/right hand detail and left/right foot pivot checks must all be `pass`.
- `needs_detail`, `uncertain`, `not_visible` and `blocker` are blocking states.
- Numeric fit diagnostics and generated screenshots are evidence, not approval.
- VLM output is evidence/signoff input only; the Skin gate still validates the schema and every required check.
- Skin setup starts only after `semanticSkinReady=true`, `stage01HandoffReady=true`, and the manual/VLM signoff is recorded.

## Review Standard

- Front view: spine, pelvis, shoulders, arms, knees and feet sit inside the visible silhouette and follow local limb centers.
- Side view: torso depth, pelvis, knees, ankles, feet and head are inside the side volume, not floating in front of or behind the mesh.
- Top view: shoulders, hands, pelvis, knees, feet and toe direction sit inside the top footprint and match model depth.
- Feet: knee bend direction, rear-foot, front-foot and toe pivots must be verified from side and top views, not inferred from front view.
- Biped `legLinks=3` exposes the foot as the ankle-to-toe Biped segment in this flow. `L_Foot/R_Foot` guide semantics are review landmarks for the foot mass, not a second ordinary Bones chain.
- Hands: single hand masses are acceptable only when no visible fingers, claws, props or sleeve details need separate Biped structure.

## Required Output

Fill `visual_review/semantic_visual_review_template.json` using `visual_review/review_schema.json`, or provide an equivalent VLM JSON to `stage01_skin_prep_gate.py --visual-signoff-json`.

`batch_stage01_fbx.ps1` will also run the optional VLM review automatically after building the evidence pack when `OPENAI_API_KEY` is set. Use `-SkipVlmReview` to force a human-only blocked handoff, or `-VisualSignoffJson` to provide a pre-reviewed JSON file.

Do not describe a run as Skin-ready unless the signoff JSON approves `stage01HandoffRecommendation=approve_for_manual_skin_setup` and all required checks are `pass`.
