/**
 * Marketing copy — the single source of truth for the landing page.
 *
 * Two rules this file exists to enforce:
 *
 * 1. **A number is said once.** Latency, voice count, and call volume used to appear
 *    five to seven times per page in five different versions, so a visitor who compared
 *    two sections saw two different products. `PERFORMANCE_STATS` is the only sample
 *    dashboard on the page, and it is labelled as an example.
 * 2. **No claim we cannot source.** Invented percentages ("+34% pipeline uplift",
 *    "94% inquiry capture", "4.9/5") were the biggest trust liability on the page: a
 *    serious buyer asks where the number came from and there was no answer. Product
 *    behaviour is described instead of scored.
 *
 * Anything that appears twice lives here once and is referenced. Anything that appears
 * nowhere is not on the page.
 */
export const NAV_LINKS = [
  { name: 'How it works', href: '#how-it-works' },
  { name: 'Capabilities', href: '#capabilities' },
  { name: 'Industries', href: '#industries' },
  { name: 'Pricing', href: '#pricing' },
  { name: 'FAQ', href: '#faq' },
];

export const HERO_CONTENT = {
  eyebrow: "AI VOICE EMPLOYEES",
  titleLine1: "Your AI employee for",
  titleHighlight: "every conversation.",
  subtitle:
    "Create, train and deploy autonomous AI voice employees that make and answer phone calls, qualify leads, and deliver real business results — around the clock, with human-like conversation.",
  ctaPrimary: "Build your agent",
  ctaSecondary: "Hear it first",
  perks: [
    "No coding required",
    "Set up in minutes",
    "Answers on the first ring",
  ],
  botTag: "Always On For Your Business",
};

/**
 * What the agent does *on* a call. Deliberately not a second list of channels —
 * inbound/outbound/bulk live in PhoneChannelsSection, and having "Answer customer
 * calls" here as well was the page repeating itself.
 */
export const AI_EMPLOYEE_CAPABILITIES = [
  {
    id: 'understand-intent',
    title: 'Understand the caller',
    desc: 'Works out what the caller actually wants — a booking, a quote, a refund, a human — instead of running a fixed decision tree.',
    icon: 'Sparkles',
    badge: 'Intent',
    highlight: 'Interrupts handled',
  },
  {
    id: 'answer-questions',
    title: 'Answer from your knowledge',
    desc: 'Every reply comes from documents you uploaded or pages you connected. If the answer is not there, it says so and books a callback.',
    icon: 'HelpCircle',
    badge: 'Knowledge',
    highlight: 'Grounded in your docs',
  },
  {
    id: 'qualify-prospects',
    title: 'Qualify against your rubric',
    desc: 'Applies your own BANT or custom criteria — budget, authority, timing, fit — and records the result on the call.',
    icon: 'CheckCircle2',
    badge: 'Qualification',
    highlight: 'Your criteria, not ours',
  },
  {
    id: 'book-appointments',
    title: 'Book and reschedule',
    desc: 'Reads live team availability, offers real slots, and writes the meeting to your calendar with the caller confirmed.',
    icon: 'Calendar',
    badge: 'Scheduling',
    highlight: 'Direct calendar sync',
  },
  {
    id: 'capture-details',
    title: 'Capture the details',
    desc: 'Pulls names, numbers, companies and requirements straight out of the conversation and files them where your team already works.',
    icon: 'Target',
    badge: 'Capture',
    highlight: 'No re-keying',
  },
  {
    id: 'handle-objections',
    title: 'Work through objections',
    desc: 'Hears a pushback and answers it using your material, then keeps the conversation moving instead of abandoning it.',
    icon: 'RotateCcw',
    badge: 'Objections',
    highlight: 'Objection handling',
  },
  {
    id: 'transfer-humans',
    title: 'Warm-transfer to a person',
    desc: 'Hands the call to a colleague with the transcript and everything captured so far, so nobody asks the customer to repeat themselves.',
    icon: 'UserCheck',
    badge: 'Handoff',
    highlight: 'Context travels with it',
  },
  {
    id: 'follow-up',
    title: 'Follow up afterwards',
    desc: 'Sends the confirmation, the reminder, or the second attempt on its own — timed by your rules, not by a human remembering.',
    icon: 'Send',
    badge: 'Follow-up',
    highlight: 'Timed by your rules',
  },
];

/** The canonical onboarding path. The page used to carry two of these, six sections apart. */
export const HOW_IT_WORKS_STEPS = [
  {
    step: '01',
    title: 'Give it a role',
    desc: 'Name your employee, define the job it does and the outcome it is accountable for.',
  },
  {
    step: '02',
    title: 'Teach it your business',
    desc: 'Connect a website or upload FAQs, product sheets and pricing so it answers from your material.',
  },
  {
    step: '03',
    title: 'Choose a voice',
    desc: 'Pick the tone that fits the customer — the console groups voices by character, not by supplier.',
  },
  {
    step: '04',
    title: 'Connect a number',
    desc: 'Claim a local or toll-free number, or bring a number you already own.',
  },
  {
    step: '05',
    title: 'Go live',
    desc: 'Take inbound calls and launch outbound follow-ups, with the transcript and outcome written up as it happens.',
  },
];

/** Telephony channels. Bulk/campaign calling has its own section, so it is not a third tab here. */
export const PHONE_CHANNELS = [
  {
    id: 'inbound',
    title: 'Inbound',
    icon: 'PhoneIncoming',
    headline: 'Your AI answers incoming calls.',
    desc: 'Calls that ring out to voicemail are revenue you already paid for. Voxly picks up, works out what the caller needs, answers from your knowledge and books the next step.',
    badge: 'First ring',
    features: [
      'Picks up on the first ring, no hold music',
      'Handles interruptions mid-sentence',
      'Books directly into your calendar',
      'Warm-transfers with full context',
    ],
    mockCaller: 'Inbound caller',
    mockGoal: 'Booking or question',
    stat: 'No missed calls',
  },
  {
    id: 'outbound',
    title: 'Outbound',
    icon: 'PhoneOutgoing',
    headline: 'Your AI calls back while interest is warm.',
    desc: 'The moment a prospect fills in a form or leaves a request, the call happens. Not tomorrow, not in a campaign, not after someone remembers.',
    badge: 'Speed to lead',
    features: [
      'Follows up within minutes of a request',
      'Reads context from your CRM before dialling',
      'Different script per record',
      'Retries the ones that did not connect',
    ],
    mockCaller: 'Recent inbound lead',
    mockGoal: 'Qualified and booked',
    stat: 'Minutes, not days',
  },
];

export const CAMPAIGN_WORKFLOW = {
  headline: 'One list. Thousands of conversations.',
  subtitle:
    'Upload a contact list, assign the employee that fits, and let it work through the whole list concurrently. Dispositions come back per contact.',
  steps: [
    { num: '1', title: 'Upload contacts', desc: 'Import a CSV or pull a list straight from your CRM' },
    { num: '2', title: 'Pick the employee', desc: 'Choose the role trained for this campaign' },
    { num: '3', title: 'Set the rules', desc: 'Calling windows, pacing and retry limits' },
    { num: '4', title: 'It calls', desc: 'Concurrent conversations, each one natural' },
    { num: '5', title: 'Read the results', desc: 'Answered, qualified and booked, per contact' },
  ],
};

/**
 * Industries, described by what the caller is actually trying to do. This used to
 * carry an invented success figure per card ("-42% no-shows", "+28% cart recovery") —
 * replaced with the concrete jobs, which are checkable.
 */
export const INDUSTRIES_DATA = [
  {
    id: 'sales',
    title: 'Sales',
    subtitle: 'Lead qualification & outbound',
    desc: 'Work inbound enquiries and call prospects back while the interest is still warm, then hand your reps something better than a name and an email address.',
    icon: 'TrendingUp',
    examples: ['B2B inbound qualification', 'Speed-to-lead follow-up', 'Quote follow-up calls'],
  },
  {
    id: 'support',
    title: 'Customer Support',
    subtitle: 'Tier-1 conversations',
    desc: 'Answer order status, billing and account questions without a queue, and bring a human in with the history attached when it needs one.',
    icon: 'Headphones',
    examples: ['Order status & tracking', 'Billing & subscription questions', 'Credential resets'],
  },
  {
    id: 'real-estate',
    title: 'Real Estate',
    subtitle: 'Enquiries & viewings',
    desc: 'Catch the buyer who called after hours about a listing, answer the amenity and price questions, and book the viewing.',
    icon: 'Building2',
    examples: ['Listing enquiry response', 'Buyer budget qualification', 'Viewing scheduling'],
  },
  {
    id: 'healthcare',
    title: 'Healthcare',
    subtitle: 'Appointments & reminders',
    desc: 'Book, reschedule and confirm appointments, and run the reminder calls that stop a booked slot turning into a no-show.',
    icon: 'Stethoscope',
    examples: ['Appointment booking', 'Pre-visit reminder calls', 'Refill request routing'],
  },
  {
    id: 'insurance',
    title: 'Insurance',
    subtitle: 'Claims & renewals',
    desc: 'Take first notice of loss, gather the details the file needs, and make renewal and coverage calls with the conversation logged.',
    icon: 'ShieldCheck',
    examples: ['First notice of loss', 'Policy renewal reminders', 'Coverage enquiry triage'],
  },
  {
    id: 'ecommerce',
    title: 'E-commerce',
    subtitle: 'Orders & abandoned carts',
    desc: 'Answer product and shipping questions on the phone, and call back the carts that were left behind.',
    icon: 'ShoppingBag',
    examples: ['Abandoned cart follow-up', 'Returns & exchanges', 'Product question calls'],
  },
];

/**
 * The one sample dashboard on the page, and it says so. Five of these used to sit in
 * five sections, each showing a different version of the same fictional business.
 */
export const PERFORMANCE_STATS = {
  headline: 'See every call, not just the ones that went well.',
  subtitle:
    'Transcripts, extracted fields, outcomes and spend, per call. Example workspace below — your numbers replace them on day one.',
  isExample: true,
  metrics: [
    { label: 'CALLS', value: '1,284', note: 'Last 30 days' },
    { label: 'ANSWERED', value: '79%', note: 'Of calls placed' },
    { label: 'QUALIFIED', value: '20%', note: 'Of calls answered' },
    { label: 'BOOKED', value: '15%', note: 'Of calls placed' },
  ],
  charts: {
    callsOverTime: [
      { month: 'May', calls: 640, resolved: 512 },
      { month: 'Jun', calls: 820, resolved: 670 },
      { month: 'Jul', calls: 980, resolved: 810 },
      { month: 'Aug', calls: 1120, resolved: 935 },
      { month: 'Sep', calls: 1284, resolved: 1023 },
    ],
    funnel: [
      { stage: 'Calls placed', count: 1284, pct: '100%' },
      { stage: 'Answered', count: 1014, pct: '79%' },
      { stage: 'Over a minute', count: 783, pct: '61%' },
      { stage: 'Qualified', count: 257, pct: '20%' },
      { stage: 'Booked', count: 193, pct: '15%' },
    ],
    outcomes: [
      { label: 'Resolved by the agent', pct: 82, color: '#6344E7' },
      { label: 'Follow-up sent', pct: 12, color: '#10B981' },
      { label: 'Transferred to a person', pct: 6, color: '#F59E0B' },
    ],
  },
};

/** Plan terms, not a fabricated account — and consistent with PRICING_TIERS below. */
export const BILLING_USAGE_PREVIEW = {
  headline: 'Pay for conversations. Know what you are spending.',
  tagline: 'Per connected second. Nothing for ringing that nobody answers.',
  items: [
    { label: 'Included minutes', value: '2,500 / mo' },
    { label: 'Overage rate', value: '$0.11 / min' },
    { label: 'Setup fee', value: '$0' },
    { label: 'Unanswered rings', value: 'Free' },
  ],
  credits: '2,500',
  minutesUsed: '2,500 / mo',
  currentUsage: '$0.11 / min',
  remainingMinutes: 'Free setup',
  billingPerSec: '$0.11/min · Billed per second',
  footnote:
    'You are billed from the moment the call connects until it ends. Ring-outs, busy signals and voicemail cost nothing.',
};

export const PRICING_TIERS = [
  {
    name: 'Starter',
    badge: 'Seed & Early Startups',
    priceMonthly: 49,
    priceAnnual: 39,
    description: 'Small teams putting their first agent on a real number.',
    features: [
      '1 AI Voice Employee',
      '500 included call minutes / month',
      '$0.14/min overage',
      'Browser voice testing',
      'Standard voice models',
      'HubSpot & Zapier basic connectors',
      'Email support',
    ],
    cta: 'Start with Starter',
    highlighted: false,
  },
  {
    name: 'Professional',
    badge: 'Most Popular',
    priceMonthly: 199,
    priceAnnual: 159,
    description: 'Growing teams running inbound qualification and follow-ups.',
    features: [
      '5 AI Voice Employees',
      '2,500 included call minutes / month',
      '$0.11/min overage',
      'Custom voice cloning & tone tuning',
      'Live webhooks & two-way CRM sync',
      'Do-Not-Call registry scrubbing',
      'Priority support',
    ],
    cta: 'Start with Professional',
    highlighted: true,
  },
  {
    name: 'Enterprise',
    badge: 'Scale & High Volume',
    priceMonthly: 699,
    priceAnnual: 549,
    description: 'High-volume programmes that need their own numbers and terms.',
    features: [
      'Unlimited AI Voice Employees',
      '10,000+ included call minutes',
      'Volume rates from $0.06/min',
      'Bring your own SIP trunk',
      'Dedicated private instance',
      'Fine-tuning on past recordings',
      'Security, compliance & SLA terms',
      'Named telephony architect',
    ],
    cta: 'Talk to us about Enterprise',
    highlighted: false,
  },
];

export const FAQS = [
  {
    q: 'How does Voxly sound so natural?',
    a: 'The same neural voice model that answers your customers calls renders every word, with natural turn-taking, so a caller can interrupt mid-sentence and be heard. You can hear it on this page — pick an industry above and press play.',
  },
  {
    q: 'Do I need engineers to deploy this?',
    a: 'No. You set the role, connect a website or upload documents, choose a voice, and attach a number. There is no code to write and no telephony hardware to install.',
  },
  {
    q: 'Can it use our own phone numbers and CRM?',
    a: 'Yes. Claim a local or toll-free number in over a hundred countries, port a number you already own, or bring your own SIP trunk. Qualified calls and transcripts are written into your CRM.',
  },
  {
    q: 'What happens when it does not know something?',
    a: 'It says so and offers a callback rather than inventing an answer. Every reply is grounded in the material you gave it, and anything outside that is escalated to a person with the transcript attached.',
  },
  {
    q: 'What does it cost?',
    a: 'A monthly plan that includes call minutes, then a per-minute overage rate. Unanswered rings, busy signals and voicemail are free. See the pricing section for current rates.',
  },
  {
    q: 'Is this compliant with calling rules?',
    a: 'Call recording and consent requirements vary by country. Compliance tooling is built in and Do-Not-Call scrubbing is available on the Professional plan and above; your counsel should confirm the obligations for the markets you call.',
  },
];