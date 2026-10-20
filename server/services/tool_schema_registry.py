"""
Tool Schema Registry - voice-pruned JSON schemas for each supported Nango integration.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

_SCHEMAS: dict[str, list[dict]] = {

    "GOOGLECALENDAR": [
        {
            "type": "function",
            "name": "GOOGLECALENDAR_CREATE_EVENT",
            "description": "Book a calendar appointment for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary":        {"type": "string", "description": "Event title / appointment name"},
                    "start":          {"type": "string", "description": "Start datetime ISO 8601"},
                    "end":            {"type": "string", "description": "End datetime ISO 8601"},
                    "attendee_email": {"type": "string", "description": "Caller email to invite"},
                    "description":    {"type": "string", "description": "Optional notes"},
                },
                "required": ["summary", "start", "end"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
            "description": "Find available time slots on a given date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "duration": {"type": "integer", "description": "Duration in minutes (default 30)"},
                },
                "required": ["date"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_FIND_SLOTS",
            "description": "Find available time slots for a given day",
            "parameters": {
                "type": "object",
                "properties": {
                    "date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "duration": {"type": "integer", "description": "Duration in minutes (default 30)"},
                },
                "required": ["date"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_LIST_EVENTS",
            "description": "List upcoming calendar events for a date",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_CANCEL_EVENT",
            "description": "Cancel or delete an existing calendar appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The Google Calendar event ID to cancel"},
                    "calendar_id": {"type": "string", "description": "Calendar identifier (default: primary)"},
                },
                "required": ["event_id"],
            },
        },
        {
            "type": "function",
            "name": "GOOGLECALENDAR_RESCHEDULE_EVENT",
            "description": "Reschedule an existing calendar appointment to a new date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The Google Calendar event ID to reschedule"},
                    "start":    {"type": "string", "description": "New start datetime ISO 8601"},
                    "end":      {"type": "string", "description": "Optional new end datetime ISO 8601"},
                    "summary":  {"type": "string", "description": "Optional updated event title"},
                },
                "required": ["event_id", "start"],
            },
        },
    ],

    "CALENDLY": [
        {
            "type": "function",
            "name": "CALENDLY_CREATE_INVITEE",
            "description": "Schedule a Calendly meeting for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_uri": {"type": "string"},
                    "invitee_email":  {"type": "string"},
                    "invitee_name":   {"type": "string"},
                    "start_time":     {"type": "string", "description": "ISO 8601"},
                },
                "required": ["invitee_email", "start_time"],
            },
        },
        {
            "type": "function",
            "name": "CALENDLY_GET_AVAILABLE_TIMES",
            "description": "Get available slots from a Calendly event type",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_uri": {"type": "string"},
                    "start_date":     {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date":       {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["event_type_uri", "start_date", "end_date"],
            },
        },
        {
            "type": "function",
            "name": "CALENDLY_CANCEL_EVENT",
            "description": "Cancel a scheduled Calendly event appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_uuid": {"type": "string", "description": "Calendly scheduled event UUID"},
                    "reason":     {"type": "string", "description": "Reason for cancellation"},
                },
                "required": ["event_uuid"],
            },
        },
        {
            "type": "function",
            "name": "CALENDLY_LIST_EVENT_TYPES",
            "description": "List available Calendly event types and durations for booking",
            "parameters": {
                "type": "object",
                "properties": {
                    "user": {"type": "string", "description": "Optional Calendly user URI"},
                },
            },
        },
    ],

    "CALCOM": [
        {
            "type": "function",
            "name": "CALCOM_CREATE_BOOKING",
            "description": "Create a cal.com booking for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "integer"},
                    "start":         {"type": "string", "description": "ISO 8601"},
                    "name":          {"type": "string"},
                    "email":         {"type": "string"},
                    "notes":         {"type": "string"},
                },
                "required": ["event_type_id", "start", "name", "email"],
            },
        },
        {
            "type": "function",
            "name": "CALCOM_GET_AVAILABLE_SLOTS",
            "description": "Get available booking slots from cal.com",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "integer"},
                    "date":          {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["event_type_id", "date"],
            },
        },
        {
            "type": "function",
            "name": "CALCOM_CANCEL_BOOKING",
            "description": "Cancel an existing Cal.com appointment booking",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_uid": {"type": "string", "description": "Cal.com booking UID"},
                    "reason":      {"type": "string", "description": "Reason for cancellation"},
                },
                "required": ["booking_uid"],
            },
        },
        {
            "type": "function",
            "name": "CALCOM_RESCHEDULE_BOOKING",
            "description": "Reschedule an existing Cal.com booking to a new start time",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_uid": {"type": "string", "description": "Cal.com booking UID"},
                    "start":       {"type": "string", "description": "New start datetime ISO 8601"},
                    "reason":      {"type": "string", "description": "Reason for rescheduling"},
                },
                "required": ["booking_uid", "start"],
            },
        },
    ],

    "SLACK": [
        {
            "type": "function",
            "name": "SLACK_SEND_MESSAGE",
            "description": "Send a Slack notification to a channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name or ID"},
                    "text":    {"type": "string", "description": "Message body"},
                },
                "required": ["channel", "text"],
            },
        },
    ],

    "HUBSPOT": [
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_CONTACT",
            "description": "Create or update a HubSpot CRM contact",
            "parameters": {
                "type": "object",
                "properties": {
                    "firstname": {"type": "string"},
                    "lastname":  {"type": "string"},
                    "email":     {"type": "string"},
                    "phone":     {"type": "string"},
                    "company":   {"type": "string"},
                },
                "required": ["firstname"],
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_LOOKUP_CONTACT",
            "description": "Look up an existing contact in HubSpot CRM by email or phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Caller email address"},
                    "phone": {"type": "string", "description": "Caller phone number"},
                },
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_DEAL",
            "description": "Create a new deal in HubSpot CRM",
            "parameters": {
                "type": "object",
                "properties": {
                    "dealname":  {"type": "string"},
                    "amount":    {"type": "number"},
                    "pipeline":  {"type": "string"},
                    "dealstage": {"type": "string"},
                },
                "required": ["dealname"],
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_UPDATE_DEAL_STAGE",
            "description": "Update the pipeline stage of an existing HubSpot deal",
            "parameters": {
                "type": "object",
                "properties": {
                    "deal_id":   {"type": "string", "description": "HubSpot deal ID"},
                    "dealstage": {"type": "string", "description": "New pipeline stage"},
                },
                "required": ["deal_id", "dealstage"],
            },
        },
        {
            "type": "function",
            "name": "HUBSPOT_CREATE_NOTE",
            "description": "Log a call note on a HubSpot contact or deal",
            "parameters": {
                "type": "object",
                "properties": {
                    "body":       {"type": "string"},
                    "contact_id": {"type": "string"},
                },
                "required": ["body"],
            },
        },
    ],

    "SALESFORCE": [
        {
            "type": "function",
            "name": "SALESFORCE_CREATE_LEAD",
            "description": "Create a Salesforce lead from call details",
            "parameters": {
                "type": "object",
                "properties": {
                    "FirstName":   {"type": "string"},
                    "LastName":    {"type": "string"},
                    "Email":       {"type": "string"},
                    "Phone":       {"type": "string"},
                    "Company":     {"type": "string"},
                    "Description": {"type": "string"},
                },
                "required": ["LastName", "Company"],
            },
        },
        {
            "type": "function",
            "name": "SALESFORCE_LOOKUP_LEAD",
            "description": "Lookup an existing lead in Salesforce by email or phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Lead email address"},
                    "phone": {"type": "string", "description": "Lead phone number"},
                },
            },
        },
        {
            "type": "function",
            "name": "SALESFORCE_CREATE_TASK",
            "description": "Log a Salesforce follow-up task",
            "parameters": {
                "type": "object",
                "properties": {
                    "Subject":      {"type": "string"},
                    "Description":  {"type": "string"},
                    "ActivityDate": {"type": "string", "description": "YYYY-MM-DD"},
                    "WhoId":        {"type": "string"},
                },
                "required": ["Subject"],
            },
        },
    ],

    "GMAIL": [
        {
            "type": "function",
            "name": "GMAIL_SEND_EMAIL",
            "description": "Send a confirmation email to the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "type": "function",
            "name": "GMAIL_CREATE_DRAFT",
            "description": "Create a draft email in Gmail for post-call review",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Subject line"},
                    "body":    {"type": "string", "description": "Email body content"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ],

    "OUTLOOKCALENDAR": [
        {
            "type": "function",
            "name": "OUTLOOKCALENDAR_CREATE_EVENT",
            "description": "Create an Outlook calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":   {"type": "string"},
                    "start":     {"type": "string", "description": "ISO 8601"},
                    "end":       {"type": "string", "description": "ISO 8601"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["subject", "start", "end"],
            },
        },
    ],

    "ZOOM": [
        {
            "type": "function",
            "name": "ZOOM_CREATE_MEETING",
            "description": "Schedule a Zoom meeting and return the join link",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic":      {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 8601"},
                    "duration":   {"type": "integer", "description": "Minutes"},
                    "agenda":     {"type": "string"},
                },
                "required": ["topic", "start_time"],
            },
        },
        {
            "type": "function",
            "name": "ZOOM_GET_MEETING",
            "description": "Retrieve details and join link for a scheduled Zoom meeting",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "string", "description": "Zoom meeting ID"},
                },
                "required": ["meeting_id"],
            },
        },
    ],

    "NOTION": [
        {
            "type": "function",
            "name": "NOTION_CREATE_PAGE",
            "description": "Create a Notion page with call notes",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string"},
                    "title":     {"type": "string"},
                    "content":   {"type": "string"},
                },
                "required": ["parent_id", "title"],
            },
        },
        {
            "type": "function",
            "name": "NOTION_SEARCH_PAGES",
            "description": "Search workspace pages or databases in Notion",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or page title"},
                },
                "required": ["query"],
            },
        },
    ],

    "AIRTABLE": [
        {
            "type": "function",
            "name": "AIRTABLE_CREATE_RECORD",
            "description": "Add a record to an Airtable base",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_id":    {"type": "string"},
                    "table_name": {"type": "string"},
                    "fields":     {"type": "object", "description": "Field key-value pairs"},
                },
                "required": ["base_id", "table_name", "fields"],
            },
        },
        {
            "type": "function",
            "name": "AIRTABLE_SEARCH_RECORDS",
            "description": "Search records in an Airtable table by formula or keyword",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_id":    {"type": "string", "description": "Airtable base ID"},
                    "table_name": {"type": "string", "description": "Table name"},
                    "filter":     {"type": "string", "description": "Optional search term or filter formula"},
                },
                "required": ["base_id", "table_name"],
            },
        },
    ],

    "ZENDESK": [
        {
            "type": "function",
            "name": "ZENDESK_CREATE_TICKET",
            "description": "Create a Zendesk support ticket",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":          {"type": "string"},
                    "comment":          {"type": "string"},
                    "requester_email":  {"type": "string"},
                    "priority":         {"type": "string", "description": "low/normal/high/urgent"},
                },
                "required": ["subject", "comment"],
            },
        },
        {
            "type": "function",
            "name": "ZENDESK_SEARCH_TICKETS",
            "description": "Search open or existing Zendesk tickets for a customer",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query, email, or ticket ID"},
                },
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": "ZENDESK_UPDATE_TICKET",
            "description": "Update status or append a comment to an existing Zendesk ticket",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Zendesk ticket ID"},
                    "comment":   {"type": "string", "description": "Comment or note to add"},
                    "status":    {"type": "string", "description": "Ticket status: open, pending, solved, closed"},
                },
                "required": ["ticket_id"],
            },
        },
    ],

    "ASANA": [
        {
            "type": "function",
            "name": "ASANA_CREATE_TASK",
            "description": "Create an Asana task from a call action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":       {"type": "string"},
                    "notes":      {"type": "string"},
                    "project_id": {"type": "string"},
                    "due_on":     {"type": "string", "description": "YYYY-MM-DD"},
                    "assignee":   {"type": "string"},
                },
                "required": ["name"],
            },
        },
        {
            "type": "function",
            "name": "ASANA_ADD_COMMENT",
            "description": "Add a note or call update to an existing Asana task",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Asana task GID"},
                    "comment": {"type": "string", "description": "Comment text to post"},
                },
                "required": ["task_id", "comment"],
            },
        },
    ],

    "LINEAR": [
        {
            "type": "function",
            "name": "LINEAR_CREATE_ISSUE",
            "description": "Create a Linear issue from a call action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "team_id":     {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=urgent 2=high 3=medium 4=low"},
                },
                "required": ["title", "team_id"],
            },
        },
        {
            "type": "function",
            "name": "LINEAR_SEARCH_ISSUES",
            "description": "Search Linear issues by title or keyword",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term or keyword"},
                },
                "required": ["query"],
            },
        },
    ],

    "JIRA": [
        {
            "type": "function",
            "name": "JIRA_CREATE_ISSUE",
            "description": "Create a Jira issue from a caller request",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "summary":     {"type": "string"},
                    "description": {"type": "string"},
                    "issue_type":  {"type": "string", "description": "Bug/Task/Story"},
                },
                "required": ["project_key", "summary"],
            },
        },
        {
            "type": "function",
            "name": "JIRA_GET_ISSUE",
            "description": "Retrieve status and details of an existing Jira issue",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key (e.g. PROJ-123)"},
                },
                "required": ["issue_key"],
            },
        },
        {
            "type": "function",
            "name": "JIRA_ADD_COMMENT",
            "description": "Add a customer note or call comment to an existing Jira issue",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key (e.g. PROJ-123)"},
                    "comment":   {"type": "string", "description": "Comment text"},
                },
                "required": ["issue_key", "comment"],
            },
        },
    ],

    "GITHUB": [
        {
            "type": "function",
            "name": "GITHUB_CREATE_ISSUE",
            "description": "Create a GitHub issue from a caller report",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner":  {"type": "string"},
                    "repo":   {"type": "string"},
                    "title":  {"type": "string"},
                    "body":   {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["owner", "repo", "title"],
            },
        },
        {
            "type": "function",
            "name": "GITHUB_SEARCH_ISSUES",
            "description": "Search issues in a GitHub repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo":  {"type": "string"},
                    "query": {"type": "string", "description": "Search keyword"},
                },
                "required": ["owner", "repo", "query"],
            },
        },
    ],

    "INTERCOM": [
        {
            "type": "function",
            "name": "INTERCOM_CREATE_CONVERSATION",
            "description": "Start an Intercom conversation for the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "email":   {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
        {
            "type": "function",
            "name": "INTERCOM_SEARCH_CONTACT",
            "description": "Search customer profile in Intercom by email",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email"},
                },
                "required": ["email"],
            },
        },
    ],

    "PIPEDRIVE": [
        {
            "type": "function",
            "name": "PIPEDRIVE_CREATE_PERSON",
            "description": "Create a Pipedrive contact",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":  {"type": "string"},
                    "email": {"type": "array", "items": {"type": "string"}},
                    "phone": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        {
            "type": "function",
            "name": "PIPEDRIVE_CREATE_DEAL",
            "description": "Create a deal in Pipedrive",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":     {"type": "string"},
                    "value":     {"type": "number"},
                    "person_id": {"type": "integer"},
                    "stage_id":  {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    ],

    "SHOPIFY": [
        {
            "type": "function",
            "name": "SHOPIFY_GET_ORDER",
            "description": "Look up a Shopify order by ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID or order number"},
                    "email":    {"type": "string", "description": "Customer email address"},
                },
            },
        },
        {
            "type": "function",
            "name": "SHOPIFY_CANCEL_ORDER",
            "description": "Cancel an unfulfilled order in Shopify",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID"},
                    "reason":   {"type": "string", "description": "Cancellation reason: customer, inventory, fraud, declined, other"},
                },
                "required": ["order_id"],
            },
        },
        {
            "type": "function",
            "name": "SHOPIFY_GET_FULFILLMENTS",
            "description": "Get shipment tracking and fulfillment status for a Shopify order",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID"},
                },
                "required": ["order_id"],
            },
        },
        {
            "type": "function",
            "name": "SHOPIFY_SEARCH_CUSTOMER",
            "description": "Search Shopify customer records by email, phone, or name",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Email, phone number, or customer name"},
                },
                "required": ["query"],
            },
        },
    ],

    "TWILIO_SMS": [
        {
            "type": "function",
            "name": "TWILIO_SMS_SEND_MESSAGE",
            "description": "Send an SMS to the caller's phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":   {"type": "string", "description": "E.164 phone number"},
                    "body": {"type": "string"},
                },
                "required": ["to", "body"],
            },
        },
        {
            "type": "function",
            "name": "TWILIO_SMS_GET_STATUS",
            "description": "Check delivery status of an SMS sent via Twilio",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_sid": {"type": "string", "description": "Twilio Message SID (SM...)"},
                },
                "required": ["message_sid"],
            },
        },
    ],

    "MICROSOFTTEAMS": [
        {
            "type": "function",
            "name": "MICROSOFTTEAMS_SEND_MESSAGE",
            "description": "Post a message to a Microsoft Teams channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "message":    {"type": "string"},
                },
                "required": ["channel_id", "message"],
            },
        },
    ],

    "CLICKUP": [
        {
            "type": "function",
            "name": "CLICKUP_CREATE_TASK",
            "description": "Create a ClickUp task from a caller action item",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id":     {"type": "string"},
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=urgent 2=high 3=normal 4=low"},
                },
                "required": ["list_id", "name"],
            },
        },
    ],

    "SENDGRID": [
        {
            "type": "function",
            "name": "SENDGRID_SEND_EMAIL",
            "description": "Send a transactional email via SendGrid",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string"},
                    "subject": {"type": "string"},
                    "body":    {"type": "string"},
                    "from_email": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ],

    "MAILCHIMP": [
        {
            "type": "function",
            "name": "MAILCHIMP_ADD_SUBSCRIBER",
            "description": "Add caller to a Mailchimp audience list",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_id":    {"type": "string"},
                    "email":      {"type": "string"},
                    "first_name": {"type": "string"},
                    "last_name":  {"type": "string"},
                },
                "required": ["list_id", "email"],
            },
        },
    ],

    "TRELLO": [
        {
            "type": "function",
            "name": "TRELLO_CREATE_CARD",
            "description": "Add a Trello card for a caller follow-up",
            "parameters": {
                "type": "object",
                "properties": {
                    "idList": {"type": "string"},
                    "name":   {"type": "string"},
                    "desc":   {"type": "string"},
                    "due":    {"type": "string", "description": "ISO 8601 due date"},
                },
                "required": ["idList", "name"],
            },
        },
    ],

    "FRESHDESK": [
        {
            "type": "function",
            "name": "FRESHDESK_LOOKUP_TICKET",
            "description": "Lookup customer support ticket by ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "email":     {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "FRESHDESK_CREATE_TICKET",
            "description": "Create a Freshdesk customer support ticket",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject":     {"type": "string"},
                    "description": {"type": "string"},
                    "email":       {"type": "string"},
                    "priority":    {"type": "integer", "description": "1=low 2=medium 3=high 4=urgent"},
                },
                "required": ["subject", "description"],
            },
        },
    ],

    "WOOCOMMERCE": [
        {
            "type": "function",
            "name": "WOOCOMMERCE_GET_ORDER",
            "description": "Lookup WooCommerce order by order ID or email",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "email":    {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "WOOCOMMERCE_CHECK_STOCK",
            "description": "Check product stock inventory by product ID or SKU",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "sku":        {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "WOOCOMMERCE_UPDATE_ORDER_STATUS",
            "description": "Update the fulfillment or processing status of a WooCommerce order",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "WooCommerce order ID"},
                    "status":   {"type": "string", "description": "New status: processing, on-hold, completed, cancelled, refunded"},
                },
                "required": ["order_id", "status"],
            },
        },
    ],

    "WHATSAPP": [
        {
            "type": "function",
            "name": "WHATSAPP_SEND_MESSAGE",
            "description": "Send a WhatsApp message or confirmation to the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string", "description": "E.164 phone number"},
                    "message": {"type": "string"},
                },
                "required": ["to", "message"],
            },
        },
    ],

    "DISCORD": [
        {
            "type": "function",
            "name": "DISCORD_SEND_MESSAGE",
            "description": "Post a message or lead summary to a Discord channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "content":    {"type": "string"},
                },
                "required": ["content"],
            },
        },
    ],

    "SUPABASE": [
        {
            "type": "function",
            "name": "SUPABASE_INSERT_ROW",
            "description": "Insert a record into a Supabase database table",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "row":   {"type": "object", "description": "Row key-values"},
                },
                "required": ["table", "row"],
            },
        },
        {
            "type": "function",
            "name": "SUPABASE_QUERY_ROW",
            "description": "Query a record from a Supabase table by column filter",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":         {"type": "string"},
                    "filter_column": {"type": "string"},
                    "filter_value":  {"type": "string"},
                },
                "required": ["table", "filter_column", "filter_value"],
            },
        },
    ],

    "MONDAY": [
        {
            "type": "function",
            "name": "MONDAY_CREATE_ITEM",
            "description": "Create an action item or lead on a Monday.com board",
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id":       {"type": "string"},
                    "item_name":      {"type": "string"},
                    "column_values":  {"type": "object"},
                },
                "required": ["item_name"],
            },
        },
    ],

    "TODOIST": [
        {
            "type": "function",
            "name": "TODOIST_CREATE_TASK",
            "description": "Create a Todoist follow-up task or reminder",
            "parameters": {
                "type": "object",
                "properties": {
                    "content":    {"type": "string"},
                    "due_string": {"type": "string"},
                    "priority":   {"type": "integer", "description": "1=normal 4=urgent"},
                },
                "required": ["content"],
            },
        },
    ],
}

# Provider-required fields must agree with what the model can supply.
for _tool in _SCHEMAS["GOOGLECALENDAR"]:
    if _tool["name"] == "GOOGLECALENDAR_RESCHEDULE_EVENT":
        _tool["parameters"]["required"] = ["event_id", "start", "end"]
        _tool["parameters"]["properties"]["end"]["description"] = "New end datetime ISO 8601 with timezone"
for _tool in _SCHEMAS["CALENDLY"]:
    if _tool["name"] == "CALENDLY_CREATE_INVITEE":
        _tool["parameters"]["properties"]["time_zone"] = {"type": "string", "description": "Invitee IANA timezone, for example Asia/Kolkata"}
        _tool["parameters"]["required"] = ["event_type_uri", "invitee_email", "start_time", "time_zone"]
for _tool in _SCHEMAS["MICROSOFTTEAMS"]:
    _tool["parameters"]["properties"]["team_id"] = {"type": "string"}
    _tool["parameters"]["required"] = ["team_id", "channel_id", "message"]
for _tool in _SCHEMAS["INTERCOM"]:
    if _tool["name"] == "INTERCOM_CREATE_CONVERSATION":
        _tool["parameters"]["properties"]["contact_id"] = {"type": "string"}
        _tool["parameters"]["anyOf"] = [{"required": ["contact_id"]}, {"required": ["email"]}]
for _tool in _SCHEMAS["PIPEDRIVE"]:
    if _tool["name"] == "PIPEDRIVE_CREATE_DEAL":
        _tool["parameters"]["properties"]["currency"] = {"type": "string", "pattern": "^[A-Z]{3}$"}
for _tool in _SCHEMAS["HUBSPOT"]:
    if _tool["name"] == "HUBSPOT_CREATE_DEAL":
        _tool["parameters"]["required"] = ["dealname", "pipeline", "dealstage"]
for _tool in _SCHEMAS["SENDGRID"]:
    _tool["parameters"]["required"] = ["to", "subject", "body", "from_email"]
for _tools in _SCHEMAS.values():
    for _tool in _tools:
        for _name, _prop in _tool["parameters"].get("properties", {}).items():
            if _prop.get("type") == "string" and _name in {"start", "end", "start_time", "end_time"}:
                _prop["format"] = "date-time"
            if _prop.get("type") == "string" and _name in {"date", "start_date", "end_date", "ActivityDate"}:
                _prop["format"] = "date"
            if _name == "duration" and _prop.get("type") == "integer":
                _prop.update(minimum=5, maximum=480)

VOICE_RESPONSE_KEYS: dict[str, tuple] = {
    "GOOGLECALENDAR":   ("status", "confirmed", "rescheduled", "date", "time", "summary", "event_id", "slots", "available", "available_slots", "busy_slots", "requested_slot", "error", "available_alternatives", "message"),
    "CALENDLY":         ("status", "booking_url", "start_time", "event_types", "event_uuid", "summary"),
    "CALCOM":           ("status", "uid", "start_time", "slots", "summary"),
    "SLACK":            ("status", "message_id", "channel", "summary"),
    "HUBSPOT":          ("status", "id", "contact_id", "deal_id", "dealstage", "contacts", "summary"),
    "SALESFORCE":       ("status", "id", "lead_id", "task_id", "leads", "summary"),
    "GMAIL":            ("status", "message_id", "draft_id", "to", "subject", "message", "summary"),
    "OUTLOOKCALENDAR":  ("status", "event_id", "date", "time", "summary"),
    "ZOOM":             ("status", "join_url", "start_time", "topic", "meeting_id", "summary"),
    "NOTION":           ("status", "page_id", "url", "results", "summary"),
    "AIRTABLE":         ("status", "record_id", "records", "summary"),
    "ZENDESK":          ("status", "ticket_id", "ticket_url", "tickets", "priority", "summary"),
    "ASANA":            ("status", "task_id", "due_on", "comment_id", "summary"),
    "LINEAR":           ("status", "issue_id", "identifier", "issues", "summary"),
    "JIRA":             ("status", "issue_id", "key", "issue_status", "summary"),
    "GITHUB":           ("status", "issue_number", "html_url", "issues", "summary"),
    "INTERCOM":         ("status", "conversation_id", "contact_id", "summary"),
    "PIPEDRIVE":        ("status", "id", "summary"),
    "SHOPIFY":          ("status", "order_id", "name", "financial_status", "fulfillment_status", "fulfillments", "customer", "tracking_number", "summary"),
    "TWILIO_SMS":       ("status", "message_sid", "delivery_status", "summary"),
    "MICROSOFTTEAMS":   ("status", "message_id", "summary"),
    "CLICKUP":          ("status", "task_id", "url", "summary"),
    "TRELLO":           ("status", "card_id", "url", "summary"),
    "SENDGRID":         ("status", "message_id", "summary"),
    "MAILCHIMP":        ("status", "subscriber_id", "summary"),
    "FRESHDESK":        ("status", "ticket_id", "subject", "priority", "tickets", "summary"),
    "WOOCOMMERCE":      ("status", "order_id", "total", "shipping_status", "stock", "summary"),
    "WHATSAPP":         ("status", "message_id", "summary"),
    "DISCORD":          ("status", "message_id", "summary"),
    "SUPABASE":         ("status", "data", "summary"),
    "MONDAY":           ("status", "item_id", "summary"),
    "TODOIST":          ("status", "task_id", "content", "summary"),
}

VOICE_RESPONSE_KEYS["GOOGLECALENDAR"] += ("events", "time_zone")
VOICE_RESPONSE_KEYS["CALENDLY"] += ("slots", "confirmed", "event_uri", "invitee_uri")


def _normalize(app_name: str) -> str:
    clean = app_name.strip().upper().replace("-", "_").replace(" ", "_")
    if clean in _SCHEMAS:
        return clean
    stripped = clean.replace("_", "")
    if stripped in _SCHEMAS:
        return stripped
    return clean


def get_tools_for_tenant(active_app_names: list[str]) -> list[dict]:
    """Return voice-pruned tool schemas for ONLY the tenant's active integrations."""
    schemas: list[dict] = []
    seen: set[str] = set()
    for raw_name in active_app_names:
        key = _normalize(raw_name)
        for schema in _SCHEMAS.get(key, []):
            tool_name = schema.get("name", "")
            if tool_name and tool_name not in seen:
                seen.add(tool_name)
                schemas.append(schema)
    return schemas


def get_tool_names_for_tenant(active_app_names: list[str]) -> set[str]:
    """Only names that have a declared schema may reach the tool router."""
    return {name for tool in get_tools_for_tenant(active_app_names) for name in (tool["name"], tool["name"].lower())}


async def get_tools_for_agent(active_apps: list[str], tenant_id: str, agent_id: str | None, factory, configured_tools: set[str] | None = None) -> list[dict]:
    """Apply agent-specific disable, timing and action rules before discovery."""
    if factory is None or not agent_id:
        return []
    import uuid
    from sqlalchemy import select
    from server.db.models.entities import Agent
    from server.db.models.integration_models import AgentIntegration
    async with factory() as session:
        owned = (await session.execute(select(Agent.agent_id).where(
            Agent.tenant_id == uuid.UUID(tenant_id), Agent.agent_id == uuid.UUID(agent_id), Agent.status == "active",
        ))).scalar_one_or_none()
        if owned is None:
            return []
        rules = (await session.execute(select(AgentIntegration).where(
            AgentIntegration.tenant_id == uuid.UUID(tenant_id), AgentIntegration.agent_id == uuid.UUID(agent_id),
        ))).scalars().all()
    configured = {_normalize(t) for t in configured_tools} if configured_tools is not None else None
    allowed = []
    for tool in get_tools_for_tenant(active_apps):
        app = tool_definition(tool["name"])[0]
        if configured is not None and tool["name"] not in configured and app not in configured:
            continue
        matching = [r for r in rules if _normalize(r.app_name) == app]
        if matching and not any(r.enabled and r.timing_mode == "in_call" and
                                (not r.action_whitelist or tool["name"] in {a.upper() for a in r.action_whitelist}) for r in matching):
            continue
        allowed.append(tool)
    return allowed


def tool_definition(tool_name: str) -> tuple[str, dict] | None:
    name = tool_name.upper()
    return next(((app, tool) for app, tools in _SCHEMAS.items() for tool in tools if tool["name"] == name), None)


@lru_cache(maxsize=128)
def _validator(tool_name: str) -> Draft202012Validator:
    definition = tool_definition(tool_name)
    if definition is None:
        raise ValueError("Unsupported integration action")
    schema = copy.deepcopy(definition[1]["parameters"])
    schema["additionalProperties"] = False
    for name, prop in schema.get("properties", {}).items():
        if prop.get("type") == "string":
            prop.setdefault("maxLength", 8000 if name.lower() in {"body", "description", "message", "content", "text"} else 2048)
            if name in schema.get("required", []):
                prop.setdefault("minLength", 1)
        if prop.get("type") == "array":
            prop.setdefault("maxItems", 25)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_tool_arguments(tool_name: str, arguments: dict) -> str | None:
    """Return a caller-safe validation error without echoing customer values."""
    if tool_definition(tool_name) is None:
        return "This integration action is not supported."
    if not isinstance(arguments, dict):
        return "Action arguments must be an object."
    try:
        if len(json.dumps(arguments, allow_nan=False).encode("utf-8")) > 16384:
            return "Action arguments are too large."
        definition = tool_definition(tool_name)[1]
        if any(isinstance(arguments.get(key), str) and not arguments[key].strip() for key in definition["parameters"].get("required", [])):
            return "Required action details are missing or invalid; ask for clarification."
        if next(_validator(tool_name).iter_errors(arguments), None) is not None:
            return "Required action details are missing or invalid; ask for clarification."
    except (TypeError, ValueError, RecursionError):
        return "Action arguments are invalid."
    return None


def get_response_keys_for_tool(tool_name: str) -> tuple:
    """Return response key whitelist for a given tool (for sanitize_voice_response)."""
    upper = tool_name.upper()
    for app_key, keys in VOICE_RESPONSE_KEYS.items():
        if upper.startswith(app_key) or upper.startswith(app_key.replace("_", "")):
            return keys
    return ("status", "summary")


def list_supported_apps() -> list[str]:
    return sorted(_SCHEMAS.keys())
