"""Full clean-fixture matrix, including disclosed negative controls."""
import asyncio
import os
import run_audit as runner
original_matrix=runner.matrix
probes = [
    dict(id="A_dnd_question_then_goodbye", business="A", kind="dnd_scope_probe", integration="none", policy="automatic", max_turns=2,
         goal="Record permanent opt-out immediately, answer the price question, retain opt-out through a later goodbye.",
         fixed_turns=["ఈ నంబర్‌కు ఇకపై ఎప్పటికీ కాల్ చేయకండి. కానీ ఇప్పుడు వంద విజిటింగ్ కార్డుల ధర ఎంత?",
                      "ధర అర్థమైంది, నాకు ఇంకేమీ అవసరం లేదు. ధన్యవాదాలు, కాల్ ముగించండి."]),
    dict(id="A_addressing_agent_name", business="A", kind="identity_probe", integration="none", policy="review", max_turns=2,
         goal="Do not store the name of the representative addressed by the caller as the caller's own name.",
         fixed_turns=["నమస్తే కవిత గారు. వంద మ్యాట్ విజిటింగ్ కార్డులకు ధర ఎంత? నా పేరు ఇంకా చెప్పలేదు.",
                      "అంతే, కావాల్సిన వివరాలు తెలిసాయి. ధన్యవాదాలు, కాల్ ముగించండి."]),
    dict(id="A_rejected_product_memory", business="A", kind="memory_probe", integration="none", policy="review", max_turns=3,
         goal="Preserve the positively selected cards and reject negated mugs as a chosen product.",
         fixed_turns=["నాకు వంద విజిటింగ్ కార్డులు కావాలి. వాటి ధర చెప్పండి.",
                      "నాకు మగ్స్ వద్దు, విజిటింగ్ కార్డులే కావాలి. నా ఎంపిక ఏదని నమోదు చేసుకున్నారు?",
                      "అంతే, నా ప్రశ్నలకు సమాధానాలు వచ్చాయి. ధన్యవాదాలు, కాల్ ముగించండి."]),
    dict(id="C_callback_withdrawn_after_question", business="C", kind="withdrawal_probe", integration="none", policy="automatic", max_turns=3,
         goal="Answer a question accompanying a callback; cancel callback when explicitly withdrawn, then close without saving it.",
         fixed_turns=["రేపు ఉదయం పది గంటలకు నాకు కాల్ చేయండి. కానీ ముందుగా Python కోర్సు ఫీజు ఎంత చెప్పండి?",
                      "నేనే తర్వాత మీకు కాల్ చేస్తాను. మీరు నాకు callback చేయవద్దు. SQL కోర్సు ఫీజు ఎంత?",
                      "అంతే, నాకు కావాల్సిన వివరాలు వచ్చాయి. ధన్యవాదాలు, కాల్ ముగించండి."]),
]
runner.matrix=lambda:[*original_matrix(), *probes]
os.environ['AUDIT_RESUME']='1'
selected=os.environ.get('REPAIR_CASES')
if selected:os.environ['AUDIT_CASES']=selected
else:os.environ.pop('AUDIT_CASES',None)
asyncio.run(runner.main())
