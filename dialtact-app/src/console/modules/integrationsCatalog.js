/**
 * Fallback copy for the integrations catalog: names, categories, plain-language
 * descriptions and the actions an agent can take. The server catalog wins where
 * it has a value; this fills the gaps.
 */
export const FULL_INTEGRATIONS_CATALOG = [
  // --- 1. SCHEDULING & CALENDARS (LIVE IN-CALL) ---
  {
    id: "GOOGLECALENDAR",
    name: "Google Calendar",
    category: "Scheduling",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Check free times, book, cancel and reschedule appointments while the caller is on the line.",
    actions: ["Find Free Slots", "Create Booking", "Cancel Event", "Reschedule Event"],
    badge: "Popular",
    iconName: "Calendar",
    color: "text-sky-500 bg-sky-500/10"
  },
  {
    id: "CALENDLY",
    name: "Calendly",
    category: "Scheduling",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Find open meeting times and book Calendly appointments for callers.",
    actions: ["Check Available Times", "Schedule Invitee Meeting", "Cancel Event", "List Event Types"],
    badge: "Popular",
    iconName: "Calendar",
    color: "text-sky-500 bg-sky-500/10"
  },
  {
    id: "CALCOM",
    name: "Cal.com",
    category: "Scheduling",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Find open times and book appointments in your Cal.com calendar.",
    actions: ["Find Available Slots", "Create Booking", "Cancel Booking", "Reschedule Booking"],
    badge: "Popular",
    iconName: "Calendar",
    color: "text-sky-500 bg-sky-500/10"
  },
  {
    id: "ZOOM",
    name: "Zoom Meetings",
    category: "Scheduling",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Create a Zoom meeting link for a caller's appointment.",
    actions: ["Create Meeting", "Get Meeting Details"],
    badge: "Video",
    iconName: "Video",
    color: "text-blue-500 bg-blue-500/10"
  },

  // --- 2. CRM & SALES (IN-CALL & POST-CALL) ---
  {
    id: "HUBSPOT",
    name: "HubSpot CRM",
    category: "CRM",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Look up the caller, create contacts and deals, and log call notes.",
    actions: ["Lookup Contact", "Create Contact", "Create Deal", "Update Deal Stage", "Log Call Note"],
    badge: "Popular",
    iconName: "Database",
    color: "text-orange-500 bg-orange-500/10"
  },
  {
    id: "SALESFORCE",
    name: "Salesforce",
    category: "CRM",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Create leads and log calls as tasks or activities in Salesforce.",
    actions: ["Create Lead", "Lookup Lead", "Create Task / Activity"],
    badge: "Sales",
    iconName: "Database",
    color: "text-blue-600 bg-blue-600/10"
  },

  // --- 3. CUSTOMER SUPPORT & HELPDESK ---
  {
    id: "ZENDESK",
    name: "Zendesk Support",
    category: "Support",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Look up open tickets and create new ones during a call.",
    actions: ["Search Tickets", "Create Ticket", "Update Ticket"],
    badge: "Popular",
    iconName: "LifeBuoy",
    color: "text-emerald-600 bg-emerald-600/10"
  },
  {
    id: "INTERCOM",
    name: "Intercom",
    category: "Support",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Search customer profiles and create conversations with caller notes.",
    actions: ["Search Contact", "Create Conversation"],
    badge: "Support",
    iconName: "MessageSquare",
    color: "text-blue-500 bg-blue-500/10"
  },
  {
    id: "JIRA",
    name: "Jira Software",
    category: "Support",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Create issue tickets and query issue status from customer voice reports.",
    actions: ["Create Issue", "Get Issue Details", "Add Comment"],
    badge: "DevOps",
    iconName: "GitBranch",
    color: "text-blue-600 bg-blue-600/10"
  },
  {
    id: "LINEAR",
    name: "Linear",
    category: "Support",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Search open issues and file problems customers report.",
    actions: ["Create Issue", "Search Issues"],
    badge: "Popular",
    iconName: "GitBranch",
    color: "text-indigo-500 bg-indigo-500/10"
  },
  {
    id: "FRESHDESK",
    name: "Freshdesk",
    category: "Support",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "api_key",
    description: "Look up customer support tickets and log new tickets during or after calls.",
    actions: ["Lookup Ticket", "Create Ticket"],
    badge: "Support",
    iconName: "LifeBuoy",
    color: "text-teal-600 bg-teal-600/10"
  },

  // --- 4. E-COMMERCE & PAYMENTS ---
  {
    id: "SHOPIFY",
    name: "Shopify",
    category: "E-Commerce",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "api_key",
    description: "Look up orders, payment and delivery status, cancel unshipped orders and find customers.",
    actions: ["Lookup Order Details", "Cancel Unfulfilled Order", "Get Fulfillments", "Search Customer"],
    badge: "Popular",
    iconName: "ShoppingBag",
    color: "text-pink-500 bg-pink-500/10"
  },
  {
    id: "WOOCOMMERCE",
    name: "WooCommerce",
    category: "E-Commerce",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "api_key",
    description: "Check WordPress store inventory stock, look up customer order status, and update order statuses.",
    actions: ["Get Order Details", "Check Product Stock", "Update Order Status"],
    badge: "Retail",
    iconName: "ShoppingBag",
    color: "text-purple-600 bg-purple-600/10"
  },

  // --- 5. TEAM COMMUNICATION & ALERTS ---
  {
    id: "SLACK",
    name: "Slack Alerts",
    category: "Communication",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Post call summaries and alerts to your team's channels.",
    actions: ["Send Channel Message"],
    badge: "Popular",
    iconName: "MessageSquare",
    color: "text-purple-600 bg-purple-600/10"
  },
  {
    id: "TWILIO_SMS",
    name: "Twilio SMS",
    category: "Communication",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "api_key",
    description: "Text callers their confirmations and booking details, and check delivery.",
    actions: ["Send SMS Message", "Check Message Status"],
    badge: "SMS",
    iconName: "MessageSquare",
    color: "text-red-500 bg-red-500/10"
  },
  {
    id: "WHATSAPP",
    name: "WhatsApp Business",
    category: "Communication",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "api_key",
    description: "Send WhatsApp follow-ups and booking confirmations to callers.",
    actions: ["Send Message"],
    badge: "Popular",
    iconName: "MessageSquare",
    color: "text-emerald-500 bg-emerald-500/10"
  },
  {
    id: "DISCORD",
    name: "Discord",
    category: "Communication",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "api_key",
    description: "Post call summaries and inbound lead notifications to staff Discord channels.",
    actions: ["Send Channel Message"],
    badge: "Community",
    iconName: "MessageSquare",
    color: "text-indigo-500 bg-indigo-500/10"
  },

  // --- 6. EMAIL FOLLOW-UPS ---
  {
    id: "GMAIL",
    name: "Gmail Follow-Up",
    category: "Email",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Send follow-up emails or save drafts after a call.",
    actions: ["Send Follow-Up Email", "Create Email Draft"],
    badge: "Popular",
    iconName: "Mail",
    color: "text-red-500 bg-red-500/10"
  },
  {
    id: "SENDGRID",
    name: "SendGrid",
    category: "Email",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "api_key",
    description: "Email callers their summaries, receipts and confirmations.",
    actions: ["Send Transactional Email"],
    badge: "Transactional",
    iconName: "Mail",
    color: "text-blue-500 bg-blue-500/10"
  },
  {
    id: "MAILCHIMP",
    name: "Mailchimp",
    category: "Email",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Add callers to email newsletter lists and capture marketing leads.",
    actions: ["Add Subscriber to List"],
    badge: "Marketing",
    iconName: "Mail",
    color: "text-amber-500 bg-amber-500/10"
  },

  // --- 7. DATABASES & SPREADSHEETS ---
  {
    id: "AIRTABLE",
    name: "Airtable",
    category: "Database",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "oauth",
    description: "Query caller records from custom Airtable bases and append structured call logs.",
    actions: ["Search Records", "Create Record"],
    badge: "Popular",
    iconName: "Database",
    color: "text-yellow-500 bg-yellow-500/10"
  },
  {
    id: "NOTION",
    name: "Notion",
    category: "Database",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Search workspace pages and create call notes in Notion databases.",
    actions: ["Search Pages", "Create Page"],
    badge: "Docs",
    iconName: "Layers",
    color: "text-stone-800 bg-stone-800/10"
  },
  {
    id: "SUPABASE",
    name: "Supabase",
    category: "Database",
    timing: "in_call",
    timing_label: "During calls",
    auth_type: "api_key",
    description: "Look up customer records and save call details in your Supabase tables.",
    actions: ["Query Rows", "Insert Row"],
    badge: "Postgres",
    iconName: "Database",
    color: "text-emerald-500 bg-emerald-500/10"
  },

  // --- 8. OPERATIONS & TASK MANAGEMENT ---
  {
    id: "ASANA",
    name: "Asana Tasks",
    category: "Productivity",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Create follow-up tasks and add call summary comments to existing tasks for team members.",
    actions: ["Create Task", "Add Task Comment"],
    badge: "Tasks",
    iconName: "Sliders",
    color: "text-rose-500 bg-rose-500/10"
  },
  {
    id: "CLICKUP",
    name: "ClickUp",
    category: "Productivity",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Create action tasks with priority assigned to team members.",
    actions: ["Create Task"],
    badge: "Productivity",
    iconName: "Sliders",
    color: "text-purple-600 bg-purple-600/10"
  },
  {
    id: "MONDAY",
    name: "Monday.com",
    category: "Productivity",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Add leads and post-call action items to Monday board workflows.",
    actions: ["Create Board Item"],
    badge: "Operations",
    iconName: "Sliders",
    color: "text-amber-500 bg-amber-500/10"
  },
  {
    id: "TODOIST",
    name: "Todoist",
    category: "Productivity",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "Add quick follow-up reminder tasks to personal or team task lists.",
    actions: ["Create Task"],
    badge: "Tasks",
    iconName: "Sliders",
    color: "text-red-500 bg-red-500/10"
  },
  {
    id: "GITHUB",
    name: "GitHub",
    category: "Productivity",
    timing: "post_call",
    timing_label: "After calls",
    auth_type: "oauth",
    description: "File issues from customer calls and search existing ones in your repositories.",
    actions: ["Create Issue", "Search Issues"],
    badge: "Dev",
    iconName: "GitBranch",
    color: "text-gray-900 bg-gray-900/10"
  }
];
