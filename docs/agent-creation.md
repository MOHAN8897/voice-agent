# Agent creation and script review

The employee wizard checks the brief before creating an agent. The authenticated
`POST /api/app/agents/analyze-brief` endpoint requires agent-write permission and
workspace membership. It does not create or publish anything.

Missing business details appear as questions in the existing creation modal. Related
details can share a question. A later answer can trigger a focused follow-up. Answers
remain visible after an error; an optional detail can explicitly be marked unavailable.
The selected language, role and call direction are supplied to the analysis already.

Creation uses `POST /api/app/agents/build-employee` with the original brief and bounded
`clarificationAnswers`. The server rechecks these source inputs rather than trusting a
client-supplied extraction. The publication pipeline has three stages:

1. Extract structured identity, company, goal, facts, workflow, permitted steps and
   constraints. Facts carry exact source evidence. Missing details remain unknown.
2. Generate a short business script from those fields. The writer does not receive
   the raw brief. It must preserve business conditions and avoid invented capabilities.
3. Review and repair the draft against the structured facts. Deterministic checks
   also reject unsupported numbers, links, unsafe instructions, mismatched English
   opening identities, placeholders and scripts over 900 words. Failed checks stop
   publication; provider failure does not silently produce a replacement script.

Extraction and review request temperature 0.2; writing requests 0.5. Providers that do
not support temperature retain their existing capability handling. Existing tenant
isolation, creation request IDs and the shared publication gate remain in effect.

Language packs, runtime system instructions, call-end policy and tool permissions
remain separate. The pasted authoring guide's automatic busy-call hangup and language
switching suggestions do not override those platform rules. Generated scripts defer
to the existing policies and never claim an action completed without tool success.

The tenant script editor shows saved/unsaved status and actionable errors. Routine
draft-check banners, internal version IDs and model diagnostics are not displayed.
Saving still validates before publication. Unsaved edits must be saved before testing.

Regression coverage: `server/tests/test_employee_script_pipeline.py`,
`server/tests/test_agent_creation_pipeline_contract.py`,
`dialtact-app/e2e/agent-clarification.spec.js`, and
`dialtact-app/e2e/primary-script-editor.spec.js`. Provider responses are controlled fixtures;
these tests do not measure live model quality or speech naturalness.
