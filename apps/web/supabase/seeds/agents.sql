-- Default copilot agent: config, agent row, and its tool set.
-- Tool names must match the tools registered in apps/api/src/gibbs/copilot/agent.py.
-- system_prompt is empty so the in-code instructions stay canonical until a
-- row edit overrides them. Idempotent; loaded on `supabase db reset`.

INSERT INTO agent.agent_config (max_output_tokens, temperature, top_p, provider_options, created_at, updated_at)
SELECT 4096, NULL, NULL, '{}'::jsonb, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM agent.agent WHERE name = 'copilot');

INSERT INTO agent.agent (name, system_prompt, foundation_model, enable_all_tools, agent_config_id, tag, description, created_at, updated_at)
SELECT 'copilot', '', NULL, false,
       (SELECT id FROM agent.agent_config ORDER BY id DESC LIMIT 1),
       'sidebar', 'The sidebar copilot: reads campaign results and fills in the new-campaign form.',
       NOW(), NOW()
ON CONFLICT (name) DO NOTHING;

INSERT INTO agent.tool_set (name, description, created_at, updated_at) VALUES
    ('copilot-core', 'Read-only campaign views plus the new-campaign form proposal tool.', NOW(), NOW())
ON CONFLICT (name) DO NOTHING;

INSERT INTO agent.tool_set_tool (tool_set_id, tool_name)
SELECT ts.id, t.name
FROM agent.tool_set ts,
     (VALUES
        ('list_campaigns'),
        ('get_campaign'),
        ('get_report'),
        ('get_hull'),
        ('get_phase_diagram'),
        ('get_candidates'),
        ('list_calculations'),
        ('get_calculation'),
        ('list_decisions'),
        ('list_elements'),
        ('propose_campaign_params')
     ) AS t(name)
WHERE ts.name = 'copilot-core'
ON CONFLICT DO NOTHING;

-- Assign the tool set to the agent
DO $$
DECLARE
    copilot_id INT;
    core_id INT;
BEGIN
    SELECT id INTO copilot_id FROM agent.agent WHERE name = 'copilot' LIMIT 1;
    SELECT id INTO core_id FROM agent.tool_set WHERE name = 'copilot-core' LIMIT 1;
    IF copilot_id IS NOT NULL AND core_id IS NOT NULL THEN
        INSERT INTO agent.agent_tool_set (agent_id, tool_set_id) VALUES (copilot_id, core_id)
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
