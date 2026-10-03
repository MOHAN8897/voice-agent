/**
 * Voxly AI — Initial Workspace Data Store
 * Provides realistic enterprise data for Agents, Phone Numbers, Calls, Leads, Campaigns, Wallet, and Settings.
 */

export const initialAgents = [
  {
    id: 'agent-maya',
    name: 'Maya',
    role: 'Inbound Receptionist',
    department: 'Customer Care',
    description: 'Handles dental clinic front desk inquiries, appointment scheduling, and insurance verification.',
    status: 'active',
    assignedNumber: '+1 (415) 555-0199',
    numberId: 'num-415-0199',
    voice: {
      provider: 'Cartesia',
      voiceId: 'sonic-british-warm',
      voiceName: 'Sarah — British Warm',
      speed: 1.02,
      pitch: 0.0,
      stability: 0.78,
    },
    language: 'English (US & UK)',
    greeting: "Thank you for calling Summit Dental Care. My name is Maya, your virtual receptionist. How can I assist with your visit today?",
    script: `You are Maya, senior dental receptionist for Summit Dental Care.
Tone: Warm, empathetic, professional, and efficient.
Objectives:
1. Greet patient politely and ask how you can help.
2. If patient wants to book or reschedule an appointment, verify their full name, phone number, and preferred day/time.
3. Check Dr. Patel's calendar and offer available morning or afternoon slots.
4. If insurance inquiry, collect carrier name and member ID for verification.
5. In case of dental emergencies (severe pain, bleeding), offer immediate priority slots or transfer to emergency triage.`,
    dynamicVariables: ['caller_name', 'service_type', 'preferred_date', 'insurance_carrier'],
    objectionRules: [
      { trigger: 'Pricing or out of pocket costs', response: 'Initial exams and consultations are covered 100% by most PPO plans. We also offer flexible interest-free payment options.' },
      { trigger: 'Fear of dental procedures', response: 'Dr. Patel specializes in gentle care and offers mild sedation options to make your visit completely comfortable.' }
    ],
    boundaries: [
      'Never diagnose specific medical conditions over the phone.',
      'Never prescribe medications.',
      'Always offer warm transfer to human nurse if patient reports acute trauma.'
    ],
    knowledgeSources: ['Summit Dental Price Sheet 2026.pdf', 'Accepted Insurance Carriers.docx'],
    stats: {
      totalCalls: 1420,
      totalMinutes: 3840,
      successRate: 94.2,
      avgDuration: '2m 45s'
    },
    updatedAt: '2026-09-18T08:30:00Z'
  },
  {
    id: 'agent-david',
    name: 'David',
    role: 'Outbound SDR',
    department: 'Sales & Revenue',
    description: 'Engages inbound marketing leads to qualify budget, authority, need, and timeline (BANT).',
    status: 'active',
    assignedNumber: '+1 (212) 555-0144',
    numberId: 'num-212-0144',
    voice: {
      provider: 'ElevenLabs',
      voiceId: 'turbo-charles-confident',
      voiceName: 'Charles — Confident SDR',
      speed: 1.05,
      pitch: -0.05,
      stability: 0.72,
    },
    language: 'English (US)',
    greeting: "Hi {{contact_name}}, this is David calling from Voxly AI. I noticed your team requested our enterprise voice fleet benchmark report. Did I catch you with two minutes?",
    script: `You are David, outbound sales development specialist for Voxly AI.
Tone: Energetic, consultative, concise, respectful of prospect time.
Objectives:
1. Confirm interest in autonomous AI voice employees for customer support or outbound campaigns.
2. Ask about current call volume and existing telephony or CRM stack.
3. Validate BANT criteria: Budget authority and decision timeline.
4. Secure agreement for a 15-minute technical architecture demonstration with our engineering leads.`,
    dynamicVariables: ['contact_name', 'company_name', 'call_volume', 'current_crm'],
    objectionRules: [
      { trigger: 'We already use a chat bot', response: 'Chatbots work well for text, but 65% of high-intent customers still prefer calling. Voxly handles real voice conversations on the phone with sub-500ms latency.' },
      { trigger: 'Not interested right now', response: 'Understood! Would it make sense if I sent a 2-minute audio sample to your email so you have it on file for next quarter?' }
    ],
    boundaries: [
      'Do not quote custom enterprise contract terms without supervisor approval.',
      'Respect Do-Not-Call (DNC) requests immediately without arguing.'
    ],
    knowledgeSources: ['Voxly Telephony Benchmark 2026.pdf', 'Competitor Comparison Battlecard.pdf'],
    stats: {
      totalCalls: 890,
      totalMinutes: 2150,
      successRate: 88.5,
      avgDuration: '2m 12s'
    },
    updatedAt: '2026-09-17T16:15:00Z'
  },
  {
    id: 'agent-elena',
    name: 'Elena',
    role: 'Tier-1 Technical Support',
    department: 'Technical Operations',
    description: 'Diagnoses SaaS connectivity, password resets, API key permissions, and billing disputes.',
    status: 'active',
    assignedNumber: '+1 (800) 555-0120',
    numberId: 'num-800-0120',
    voice: {
      provider: 'Deepgram',
      voiceId: 'aura-stella-clear',
      voiceName: 'Stella — Crisp Enterprise',
      speed: 1.0,
      pitch: 0.0,
      stability: 0.85,
    },
    language: 'English, Telugu & Hindi',
    greeting: "Hello, thank you for reaching Voxly Technical Support. I am Elena. What technical issue or API endpoint can I assist you with today?",
    script: `You are Elena, Tier-1 technical support engineer for cloud developers.
Tone: Calm, analytical, patient, solution-oriented.
Objectives:
1. Identify customer workspace ID and affected service.
2. Troubleshoot WebRTC connection errors, SIP registration, or webhook delivery failures.
3. Provide step-by-step resolution from knowledge base.
4. If unresolved after 3 minutes or server outage detected, escalate to on-call DevOps engineer with warm transfer.`,
    dynamicVariables: ['workspace_id', 'service_name', 'error_code'],
    objectionRules: [
      { trigger: 'System seems down', response: 'Our real-time status page shows 99.98% uptime across all regional media gateways. Let me run a diagnostic test on your specific SIP trunk.' }
    ],
    boundaries: [
      'Never request customer passwords or raw private API keys.',
      'Always log support ticket ID in CRM.'
    ],
    knowledgeSources: ['Voxly API Documentation v2.pdf', 'WebRTC Troubleshooting Guide.docx'],
    stats: {
      totalCalls: 1120,
      totalMinutes: 4210,
      successRate: 91.8,
      avgDuration: '3m 45s'
    },
    updatedAt: '2026-09-18T10:00:00Z'
  },
  {
    id: 'agent-jordan',
    name: 'Jordan',
    role: 'Loan Officer & Debt Advisor',
    department: 'Financial Services',
    description: 'Confirms loan pre-qualifications, gathers credit requirements, and sets repayment schedules.',
    status: 'paused',
    assignedNumber: null,
    numberId: null,
    voice: {
      provider: 'PlayHT',
      voiceId: 'play3-jordan-calm',
      voiceName: 'Jordan — Measured & Trustworthy',
      speed: 0.98,
      pitch: -0.1,
      stability: 0.82,
    },
    language: 'English & Spanish',
    greeting: "Good day. This is Jordan from Summit Financial Lending. Am I speaking with {{contact_name}} regarding your recent small business capital application?",
    script: `You are Jordan, loan qualification specialist.
Tone: Respectful, compliant, reassuring, highly accurate.
Objectives:
1. Confirm identity using last 4 digits of phone number.
2. Verify business gross monthly revenue and requested loan amount.
3. Check pre-qualification underwriting criteria.
4. Schedule final underwriting review with senior loan officer.`,
    dynamicVariables: ['contact_name', 'loan_amount', 'business_revenue'],
    objectionRules: [
      { trigger: 'Interest rate too high', response: 'Our rates start at prime plus 1.5% with zero prepayment penalties. We will model three terms during your underwriting review.' }
    ],
    boundaries: [
      'Adhere strictly to Truth in Lending Act (TILA) guidelines.',
      'Never guarantee formal loan approval before credit check.'
    ],
    knowledgeSources: ['Underwriting Guidelines 2026.pdf'],
    stats: {
      totalCalls: 412,
      totalMinutes: 1090,
      successRate: 85.0,
      avgDuration: '2m 38s'
    },
    updatedAt: '2026-09-15T12:00:00Z'
  }
];

export const initialPhoneNumbers = [
  {
    id: 'num-415-0199',
    number: '+1 (415) 555-0199',
    formatted: '+14155550199',
    country: 'United States',
    countryCode: 'US',
    type: 'Local DID',
    areaCode: '415',
    locality: 'San Francisco, CA',
    assignedAgentId: 'agent-maya',
    assignedAgentName: 'Maya',
    monthlyCost: 2.50,
    status: 'active',
    capabilities: ['Voice', 'SMS'],
    usageMinutesThisMonth: 840,
    emergencyAddress: '100 Montgomery St, Suite 400, San Francisco, CA 94104',
    inboundRouting: {
      action: 'ai_agent',
      greetingPhrase: 'Welcome to Summit Dental Care. Connecting you with Maya...',
      businessHours: '08:00 - 18:00 (PST)',
      afterHoursAction: 'voicemail',
      recordingEnabled: true
    }
  },
  {
    id: 'num-212-0144',
    number: '+1 (212) 555-0144',
    formatted: '+12125550144',
    country: 'United States',
    countryCode: 'US',
    type: 'Local DID',
    areaCode: '212',
    locality: 'New York, NY',
    assignedAgentId: 'agent-david',
    assignedAgentName: 'David',
    monthlyCost: 2.50,
    status: 'active',
    capabilities: ['Voice'],
    usageMinutesThisMonth: 1210,
    emergencyAddress: '350 5th Ave, New York, NY 10118',
    inboundRouting: {
      action: 'ai_agent',
      greetingPhrase: 'Voxly Sales Development line. Connecting with David...',
      businessHours: '09:00 - 19:00 (EST)',
      afterHoursAction: 'voicemail',
      recordingEnabled: true
    }
  },
  {
    id: 'num-800-0120',
    number: '+1 (800) 555-0120',
    formatted: '+18005550120',
    country: 'United States',
    countryCode: 'US',
    type: 'Toll-Free',
    areaCode: '800',
    locality: 'Nationwide (Toll-Free)',
    assignedAgentId: 'agent-elena',
    assignedAgentName: 'Elena',
    monthlyCost: 4.50,
    status: 'active',
    capabilities: ['Voice', 'SMS'],
    usageMinutesThisMonth: 1840,
    emergencyAddress: '100 Montgomery St, San Francisco, CA 94104',
    inboundRouting: {
      action: 'ai_agent',
      greetingPhrase: 'Thank you for calling Technical Support. Elena is listening...',
      businessHours: '24/7 Priority Support',
      afterHoursAction: 'ai_agent',
      recordingEnabled: true
    }
  },
  {
    id: 'num-512-0188',
    number: '+1 (512) 555-0188',
    formatted: '+15125550188',
    country: 'United States',
    countryCode: 'US',
    type: 'Local DID',
    areaCode: '512',
    locality: 'Austin, TX',
    assignedAgentId: null,
    assignedAgentName: 'Unassigned (Pool)',
    monthlyCost: 2.50,
    status: 'idle',
    capabilities: ['Voice'],
    usageMinutesThisMonth: 110,
    emergencyAddress: '500 E 4th St, Austin, TX 78701',
    inboundRouting: {
      action: 'voicemail',
      greetingPhrase: 'Summit Finance pool line. Please leave a message.',
      businessHours: '09:00 - 17:00 (CST)',
      afterHoursAction: 'voicemail',
      recordingEnabled: true
    }
  }
];

export const initialCalls = [
  {
    id: 'call-98214',
    callerPhone: '+1 (650) 412-9912',
    callerName: 'Mark Henderson',
    direction: 'Inbound',
    agentId: 'agent-maya',
    agentName: 'Maya',
    virtualNumber: '+1 (415) 555-0199',
    durationSeconds: 165,
    formattedDuration: '2m 45s',
    outcome: 'Appointment Scheduled',
    status: 'Qualified',
    sentiment: 'Positive',
    sentimentScore: 0.88,
    timestamp: '12 mins ago',
    date: '2026-09-18 12:15',
    cost: '$0.26',
    audioUrl: '/audio/sample-call-01.mp3',
    summary: 'Mark scheduled a routine dental hygiene and examination visit for Thursday, Sept 24 at 2:00 PM. Verified Delta Dental insurance.',
    intent: 'Appointment Scheduling',
    extractedFields: {
      patientName: 'Mark Henderson',
      appointmentDate: '2026-09-24 14:00',
      insurance: 'Delta Dental PPO',
      actionTaken: 'Calendar event created & SMS sent'
    },
    transcript: [
      { speaker: 'Maya', time: '00:02', text: 'Thank you for calling Summit Dental Care. My name is Maya, your virtual receptionist. How can I assist with your visit today?' },
      { speaker: 'Caller', time: '00:08', text: 'Hi Maya, I need to book an appointment for a routine cleaning and checkup next week.' },
      { speaker: 'Maya', time: '00:15', text: 'I would be happy to schedule that for you! May I have your full name please?' },
      { speaker: 'Caller', time: '00:20', text: 'Yes, it is Mark Henderson.' },
      { speaker: 'Maya', time: '00:25', text: 'Thank you Mark. We have an opening on Thursday, September 24th at 2:00 PM with Dr. Patel. Does that time work well for you?' },
      { speaker: 'Caller', time: '00:34', text: 'Thursday at 2:00 PM sounds perfect.' },
      { speaker: 'Maya', time: '00:40', text: 'Wonderful. I have reserved that slot. I am sending a confirmation text to this number with all clinic details. Is there anything else I can help with?' },
      { speaker: 'Caller', time: '00:50', text: 'No, that was very fast. Thank you!' },
      { speaker: 'Maya', time: '00:54', text: 'You are very welcome Mark. We look forward to seeing you Thursday. Have a great day!' }
    ]
  },
  {
    id: 'call-98213',
    callerPhone: '+1 (212) 883-4910',
    callerName: 'Sarah Jenkins',
    direction: 'Outbound',
    agentId: 'agent-david',
    agentName: 'David',
    virtualNumber: '+1 (212) 555-0144',
    durationSeconds: 132,
    formattedDuration: '2m 12s',
    outcome: 'Lead Qualified (BANT 85)',
    status: 'Qualified',
    sentiment: 'Positive',
    sentimentScore: 0.82,
    timestamp: '48 mins ago',
    date: '2026-09-18 11:38',
    cost: '$0.21',
    audioUrl: '/audio/sample-call-02.mp3',
    summary: 'Sarah confirmed Apex Logistics handles 12,000 monthly support calls. Interested in 50-agent automated dispatch. Scheduled live engineering demo.',
    intent: 'Enterprise Sales Qualification',
    extractedFields: {
      prospectName: 'Sarah Jenkins',
      company: 'Apex Logistics',
      callVolume: '12,000 / mo',
      actionTaken: 'HubSpot Deal Created: $4,500/mo'
    },
    transcript: [
      { speaker: 'David', time: '00:02', text: 'Hi Sarah, this is David from Voxly AI. I noticed you downloaded our enterprise voice fleet whitepaper. Did I catch you with a quick minute?' },
      { speaker: 'Caller', time: '00:09', text: 'Hi David. Yes, we are actually looking at replacing our IVR system for driver dispatch.' },
      { speaker: 'David', time: '00:16', text: 'That is right in our wheelhouse. How many monthly inbound calls does your dispatch desk manage currently?' },
      { speaker: 'Caller', time: '00:24', text: 'Around twelve thousand calls each month across 40 logistics hubs.' },
      { speaker: 'David', time: '00:31', text: 'Got it. Voxly can handle that volume autonomously with sub-500ms voice response. Let us set up a live 15-minute engineering demo with our solutions architect. Would tomorrow morning work?' },
      { speaker: 'Caller', time: '00:44', text: 'Yes, 10:00 AM EST works for our VP of Operations.' }
    ]
  },
  {
    id: 'call-98212',
    callerPhone: '+1 (408) 772-1920',
    callerName: 'Alex Chen',
    direction: 'Inbound',
    agentId: 'agent-elena',
    agentName: 'Elena',
    virtualNumber: '+1 (800) 555-0120',
    durationSeconds: 228,
    formattedDuration: '3m 48s',
    outcome: 'Resolved (API Rate Limit)',
    status: 'Resolved',
    sentiment: 'Neutral',
    sentimentScore: 0.55,
    timestamp: '2 hours ago',
    date: '2026-09-18 10:20',
    cost: '$0.36',
    audioUrl: '/audio/sample-call-03.mp3',
    summary: 'Alex reported HTTP 429 errors on outbound call triggers. Elena identified concurrent line limit cap and guided API key upgrade in settings.',
    intent: 'Technical API Support',
    extractedFields: {
      client: 'CloudVoice Labs',
      errorCode: 'HTTP 429 Too Many Requests',
      actionTaken: 'Increased burst limit to 50 TPS'
    },
    transcript: [
      { speaker: 'Elena', time: '00:02', text: 'Hello, thank you for reaching Voxly Technical Support. I am Elena. What technical issue or API endpoint can I assist you with today?' },
      { speaker: 'Caller', time: '00:10', text: 'Hi Elena, our campaign API is throwing 429 errors when initiating batch calls.' },
      { speaker: 'Elena', time: '00:18', text: 'I understand. Let me check your workspace concurrency allocation. May I have your workspace ID?' },
      { speaker: 'Caller', time: '00:26', text: 'It is ws-cloudvoice-08.' },
      { speaker: 'Elena', time: '00:32', text: 'Thank you Alex. Your account was capped at 10 concurrent lines. I have temporarily raised your burst concurrency ceiling to 50 so your campaign can proceed without disruption.' }
    ]
  },
  {
    id: 'call-98211',
    callerPhone: '+1 (702) 991-3829',
    callerName: 'Unknown Caller',
    direction: 'Outbound',
    agentId: 'agent-david',
    agentName: 'David',
    virtualNumber: '+1 (212) 555-0144',
    durationSeconds: 18,
    formattedDuration: '18s',
    outcome: 'Voicemail Drop Left',
    status: 'Voicemail',
    sentiment: 'Neutral',
    sentimentScore: 0.50,
    timestamp: '3 hours ago',
    date: '2026-09-18 09:12',
    cost: '$0.03',
    audioUrl: '/audio/sample-call-04.mp3',
    summary: 'Answering machine detected in 1100ms. Injected personalized voicemail drop after beep tone. Automated retry scheduled for tomorrow.',
    intent: 'Outbound Campaign Dial',
    extractedFields: {
      actionTaken: 'Voicemail audio dropped; retry in 24h'
    },
    transcript: [
      { speaker: 'System', time: '00:01', text: '[Carrier 200 OK connected]' },
      { speaker: 'System', time: '00:03', text: '[AMD: Answering Machine Detected - 98% confidence]' },
      { speaker: 'Voicemail', time: '00:08', text: 'Please leave a message after the tone. [BEEP]' },
      { speaker: 'David', time: '00:11', text: 'Hi, this is David from Voxly AI calling regarding your team inquiry. You can reach us back directly at 212-555-0144. Have a wonderful day.' }
    ]
  }
];

export const initialLeads = [
  {
    id: 'lead-01',
    name: 'Mark Henderson',
    company: 'Self / Private Patient',
    phone: '+1 (650) 412-9912',
    email: 'mark.henderson@gmail.com',
    source: 'Inbound Call (Summit Dental)',
    agentId: 'agent-maya',
    agentName: 'Maya',
    stage: 'Meeting Booked',
    bantScore: 92,
    intent: 'Dental Hygiene & Exam',
    lastCallDate: 'Today, 12:15 PM',
    nextAction: 'Appointment on Thursday Sep 24 at 2:00 PM',
    notes: 'Delta Dental PPO patient. Prefers afternoon appointments. High intent.'
  },
  {
    id: 'lead-02',
    name: 'Sarah Jenkins',
    company: 'Apex Logistics Corp',
    phone: '+1 (212) 883-4910',
    email: 'sjenkins@apexlogistics.com',
    source: 'Outbound Campaign (Q4 SDR)',
    agentId: 'agent-david',
    agentName: 'David',
    stage: 'Qualified',
    bantScore: 85,
    intent: '50-Seat Voice Dispatcher Fleet',
    lastCallDate: 'Today, 11:38 AM',
    nextAction: 'Schedule 15-min solutions architect demo',
    notes: 'Manages 12,000 calls/mo across 40 distribution centers. Budget approved for Q4.'
  },
  {
    id: 'lead-03',
    name: 'Dr. Robert Vance',
    company: 'Vance Orthopedics',
    phone: '+1 (512) 441-2910',
    email: 'rvance@vanceortho.com',
    source: 'Inbound Call (Reception Line)',
    agentId: 'agent-maya',
    agentName: 'Maya',
    stage: 'Contacted',
    bantScore: 78,
    intent: 'After-Hours Patient Triage',
    lastCallDate: 'Yesterday, 4:10 PM',
    nextAction: 'Send HIPAA security BAA agreement to email',
    notes: 'Looking for 24/7 autonomous triage agent to reduce physician on-call burnout.'
  },
  {
    id: 'lead-04',
    name: 'David Miller',
    company: 'Miller & Co Realty',
    phone: '+1 (312) 990-1284',
    email: 'dmiller@millerrealty.com',
    source: 'Outbound Campaign (Real Estate Leads)',
    agentId: 'agent-david',
    agentName: 'David',
    stage: 'New',
    bantScore: 64,
    intent: 'Inbound Buyer Lead Responder',
    lastCallDate: '2 days ago',
    nextAction: 'Follow-up call on Friday morning',
    notes: 'Interested in instant voice response for Zillow inquiries.'
  },
  {
    id: 'lead-05',
    name: 'Out of Area Inquiry',
    company: 'Unregistered',
    phone: '+1 (702) 119-0021',
    email: null,
    source: 'Inbound Call',
    agentId: 'agent-maya',
    agentName: 'Maya',
    stage: 'Unqualified',
    bantScore: 22,
    intent: 'Out of State Service',
    lastCallDate: '3 days ago',
    nextAction: 'None (Archived)',
    notes: 'Caller located in Nevada; clinic licenses are strictly California.'
  }
];

export const initialCampaigns = [
  {
    id: 'camp-q4-dental',
    name: 'Q4 Dental Patient Reactivation',
    objective: 'Reactivate past patients due for 6-month hygiene recall checkups',
    agentId: 'agent-maya',
    agentName: 'Maya',
    status: 'running',
    assignedNumber: '+1 (415) 555-0199',
    totalContacts: 1250,
    completedCalls: 680,
    connectedCalls: 312,
    answerRate: 45.8,
    leadsGenerated: 142,
    costIncurred: '$71.40',
    callingHours: '09:00 - 18:00 (Local Recipient Time)',
    concurrencyLimit: 20,
    retryRules: 'Max 3 retries, spaced 4 hours apart',
    progressPercent: 54,
    createdAt: '2026-09-16'
  },
  {
    id: 'camp-enterprise-sdr',
    name: 'SaaS Inbound Whitepaper Follow-up',
    objective: 'Qualify enterprise downloads of 2026 Voice AI Telephony benchmark report',
    agentId: 'agent-david',
    agentName: 'David',
    status: 'paused',
    assignedNumber: '+1 (212) 555-0144',
    totalContacts: 500,
    completedCalls: 340,
    connectedCalls: 156,
    answerRate: 45.9,
    leadsGenerated: 48,
    costIncurred: '$36.20',
    callingHours: '10:00 - 17:00 (EST)',
    concurrencyLimit: 15,
    retryRules: 'Max 2 retries on busy or no-answer',
    progressPercent: 68,
    createdAt: '2026-09-14'
  }
];

export const initialWallet = {
  remainingMinutes: 1248,
  usdEquivalent: 118.56,
  ratePerMinute: 0.095,
  ratePerSecond: 0.001583,
  autoRechargeEnabled: true,
  autoRechargeThresholdUsd: 20.00,
  autoRechargeAmountUsd: 100.00,
  emergencyOverdraftUsd: 15.00,
  defaultPaymentMethod: {
    brand: 'Visa',
    last4: '4242',
    expMonth: 12,
    expYear: 2028
  },
  costLedger: [
    { id: 'tx-01', timestamp: 'Today, 12:15 PM', agent: 'Maya', durationSeconds: 165, telecom: '$0.033', stt: '$0.019', llm: '$0.068', tts: '$0.126', total: '$0.246' },
    { id: 'tx-02', timestamp: 'Today, 11:38 AM', agent: 'David', durationSeconds: 132, telecom: '$0.026', stt: '$0.015', llm: '$0.055', tts: '$0.101', total: '$0.197' },
    { id: 'tx-03', timestamp: 'Today, 10:20 AM', agent: 'Elena', durationSeconds: 228, telecom: '$0.045', stt: '$0.026', llm: '$0.095', tts: '$0.174', total: '$0.340' },
    { id: 'tx-04', timestamp: 'Today, 09:12 AM', agent: 'David', durationSeconds: 18, telecom: '$0.004', stt: '$0.002', llm: '$0.007', tts: '$0.014', total: '$0.027' }
  ]
};

export const availableNumbersCatalog = [
  { number: '+1 (415) 555-0233', formatted: '+14155550233', locality: 'San Francisco, CA', areaCode: '415', country: 'US', type: 'Local DID', fee: 2.50, features: ['Voice', 'SMS'] },
  { number: '+1 (415) 555-0481', formatted: '+14155550481', locality: 'San Francisco, CA', areaCode: '415', country: 'US', type: 'Local DID', fee: 2.50, features: ['Voice', 'SMS'] },
  { number: '+1 (212) 555-0399', formatted: '+12125550399', locality: 'New York, NY', areaCode: '212', country: 'US', type: 'Local DID', fee: 2.50, features: ['Voice'] },
  { number: '+1 (312) 555-0711', formatted: '+13125550711', locality: 'Chicago, IL', areaCode: '312', country: 'US', type: 'Local DID', fee: 2.50, features: ['Voice', 'SMS'] },
  { number: '+1 (800) 555-0344', formatted: '+18005550344', locality: 'Nationwide (Toll-Free)', areaCode: '800', country: 'US', type: 'Toll-Free', fee: 4.50, features: ['Voice', 'SMS'] },
  { number: '+1 (888) 555-0919', formatted: '+18885550919', locality: 'Nationwide (Toll-Free)', areaCode: '888', country: 'US', type: 'Toll-Free', fee: 4.50, features: ['Voice'] }
];
