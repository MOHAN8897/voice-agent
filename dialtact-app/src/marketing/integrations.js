import {
  siAirtable, siAsana, siCaldotcom, siCalendly, siClickup, siDiscord, siGithub, siGmail, siGooglecalendar,
  siHubspot, siIntercom, siJira, siLinear, siMailchimp, siNotion, siShopify, siSupabase, siTodoist,
  siWhatsapp, siWoocommerce, siZendesk, siZoom,
} from 'simple-icons';

/**
 * The integrations an agent can use, as the server catalog lists them
 * (server/routes/integrations_catalog.py). The telephony carrier's SMS integration is
 * left off: the site never names carriers (scripts/check-landing-copy.mjs). Logos are
 * Simple Icons (CC0); the few brands Simple Icons does not carry get their initials,
 * never a look-alike logo.
 */
export const INTEGRATIONS = [
  { name: 'Google Calendar', category: 'Calendars', icon: siGooglecalendar },
  { name: 'Calendly', category: 'Calendars', icon: siCalendly },
  { name: 'Cal.com', category: 'Calendars', icon: siCaldotcom },
  { name: 'Zoom', category: 'Calendars', icon: siZoom },
  { name: 'HubSpot', category: 'CRM', icon: siHubspot },
  { name: 'Salesforce', category: 'CRM', mark: 'Sf' },
  { name: 'Zendesk', category: 'Helpdesk', icon: siZendesk },
  { name: 'Intercom', category: 'Helpdesk', icon: siIntercom },
  { name: 'Freshdesk', category: 'Helpdesk', mark: 'Fd' },
  { name: 'Jira', category: 'Helpdesk', icon: siJira },
  { name: 'Linear', category: 'Helpdesk', icon: siLinear },
  { name: 'Shopify', category: 'Commerce', icon: siShopify },
  { name: 'WooCommerce', category: 'Commerce', icon: siWoocommerce },
  { name: 'Slack', category: 'Messaging', mark: 'Sl' },
  { name: 'WhatsApp Business', category: 'Messaging', icon: siWhatsapp },
  { name: 'Discord', category: 'Messaging', icon: siDiscord },
  { name: 'Gmail', category: 'Email', icon: siGmail },
  { name: 'Mailchimp', category: 'Email', icon: siMailchimp },
  { name: 'SendGrid', category: 'Email', mark: 'Sg' },
  { name: 'Airtable', category: 'Data', icon: siAirtable },
  { name: 'Notion', category: 'Data', icon: siNotion },
  { name: 'Supabase', category: 'Data', icon: siSupabase },
  { name: 'Asana', category: 'Tasks', icon: siAsana },
  { name: 'ClickUp', category: 'Tasks', icon: siClickup },
  { name: 'Monday.com', category: 'Tasks', mark: 'Mo' },
  { name: 'Todoist', category: 'Tasks', icon: siTodoist },
  { name: 'GitHub', category: 'Tasks', icon: siGithub },
];
