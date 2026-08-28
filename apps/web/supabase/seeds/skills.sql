-- Materials-science skill set for the copilot. Skills are documents the agent
-- loads on demand with `load_skill`; they inform setup and interpretation and
-- never substitute for tool results. Idempotent; loaded on `supabase db reset`.

INSERT INTO agent.skill_set (name, description, created_at, updated_at) VALUES
    ('materials-science', 'Setup recipes and interpretation guides for alloy stability campaigns.', NOW(), NOW())
ON CONFLICT (name) DO NOTHING;

INSERT INTO agent.skill_set_skill (skill_set_id, skill_name, description, content)
SELECT ss.id, s.name, s.description, s.content
FROM agent.skill_set ss,
     (VALUES
        ('cu-au-order-disorder',
         'How to set up and sanity-check a Cu-Au ordering / phase-diagram campaign against measured data.',
$skill$# Cu–Au order/disorder campaigns

Cu–Au is the textbook FCC ordering system and the platform's real-data validation target.

## Known experimental facts (literature, not campaign results)
- Ordered phases on the FCC lattice: Cu3Au (L1_2, x_Au = 0.25), CuAu (L1_0, x_Au = 0.5), CuAu3 (L1_2, x_Au = 0.75).
- Order/disorder temperatures: Cu3Au ≈ 663 K, CuAu ≈ 683 K (L1_0 → disordered), CuAu3 ≈ 470–500 K.
- Lattice constants: Cu 3.61 Å, Au 4.08 Å; the size mismatch drives a real L1_0 tetragonal distortion (c/a ≈ 0.93) that a rigid FCC lattice cannot capture.

## Setting up
- Elements: A = Cu, B = Au (x is the Au fraction). EMT supports both; Quantum ESPRESSO needs the Cu and Au pseudopotentials on disk.
- Hull discovery (dft_v3): budget 12–20 is enough to pin the three ordered phases; endpoints are measured first automatically.
- Finite-temperature ordering: the T_c(x) sweep on a *fitted* cluster expansion is not yet a campaign stage (phase_v2 today runs on a hidden CE and is a benchmark). Until it lands, report the 0 K hull and quote the experimental transition temperatures as literature context.
- Strategy: uncertainty sampling is the strongest default; use agent when the scientist wants narrated decisions.

## Interpreting
- Expect the CE + Monte Carlo T_c to overshoot experiment by ~10–25 %: vibrational entropy and the L1_0 distortion are missing. Reproducing that known bias is a stronger validation than agreement would be.
- Formation energies from EMT are smaller in magnitude than DFT/experiment (≈ −0.05 eV/atom for Cu3Au experimentally); say which engine produced the number.
$skill$),
        ('hull-interpretation',
         'Reading a formation-energy convex hull and judging whether the cluster expansion can be trusted.',
$skill$# Reading a formation-energy hull

- Points on the lower convex hull are predicted ground states at 0 K; energy above hull (e_above_hull) measures metastability — below ~0.02 eV/atom is "close to stable" and worth verifying.
- A structure counts as *measured* only if a calculation succeeded for it; everything else is a cluster-expansion (CE) prediction with a bootstrap σ.
- Trust signals for the CE: LOOCV RMSE well below the spread of formation energies (rule of thumb: < 0.01 eV/atom for real engines, < 10 % of the hull depth for hidden models); σ shrinking on repeated fits; endpoints measured.
- Warning signs: LOOCV comparable to the hull depth, predicted-stable set changing every model version, large σ on the candidates that matter. Recommend more measurements near the suspect compositions rather than concluding.
- Hidden-Hamiltonian campaigns (alloy_v1, fcc_v2, property_v3 with the hidden engine) report dimensionless model energies — never call them eV.
- Always cite the calculation behind a measured point: [calc:<id>].
$skill$),
        ('scf-failure-triage',
         'What Quantum ESPRESSO failure categories mean and which parameter change to propose.',
$skill$# SCF failure triage (Quantum ESPRESSO)

Failure categories recorded on calculations:
- SCF_NOT_CONVERGED — the electronic self-consistency loop hit electron_maxstep. Typical causes: too-aggressive mixing on a metal, too few k-points, cutoff below the pseudopotential's requirement. Fixes in order: raise electron_maxstep (×1.5–2), lower mixing_beta (0.4 → 0.2–0.3) with local-TF mixing, then denser k-points.
- PW_RUNTIME_ERROR — pw.x aborted with an explicit error in the log (missing pseudopotential, bad cell, out of memory). Read the log tail via get_calculation; the fix is usually configuration, not a retry.
- ENGINE_CRASH — the process died without a QE error message (killed, OOM, timeout). Retry once unchanged; if it recurs, reduce the cell size or the volume-scan span.
- INFRASTRUCTURE_FAILURE — the worker or job runner failed, not the physics; the platform retries these automatically.

The platform's retry policy already applies electron_maxstep and mixing_beta factors; check `changed_parameters` on the retry before proposing the same change again. Scientific failures are data — a structure that will not converge at a coarse setting is worth noting in the report.
$skill$)
     ) AS s(name, description, content)
WHERE ss.name = 'materials-science'
ON CONFLICT (skill_set_id, skill_name) DO NOTHING;

-- Assign the skill set to the copilot
DO $$
DECLARE
    copilot_id INT;
    ms_id INT;
BEGIN
    SELECT id INTO copilot_id FROM agent.agent WHERE name = 'copilot' LIMIT 1;
    SELECT id INTO ms_id FROM agent.skill_set WHERE name = 'materials-science' LIMIT 1;
    IF copilot_id IS NOT NULL AND ms_id IS NOT NULL THEN
        INSERT INTO agent.agent_skill_set (agent_id, skill_set_id) VALUES (copilot_id, ms_id)
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
