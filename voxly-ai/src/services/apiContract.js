/**
 * Voxly AI — OpenAPI 3.0 API Specification & Data Contracts
 * 
 * Provides strict schema definitions, DTO types, and request/response
 * contracts for every endpoint across the Voxly User Console.
 */

export const openApiSpec = {
  openapi: '3.0.3',
  info: {
    title: 'Voxly AI Voice Platform API',
    version: '1.0.0',
    description: 'Enterprise REST API for autonomous AI Voice Employees, PSTN Telephony DIDs, Live SIP Routing, Call Transcripts, and CRM Pipeline Sync.'
  },
  servers: [
    { url: 'https://api.voxly.ai/v1', description: 'Production Gateway' },
    { url: 'http://localhost:8000/api', description: 'Local Backend Server' }
  ],
  paths: {
    '/api/auth/login': {
      post: {
        summary: 'Authenticate user with email and password',
        tags: ['Authentication'],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['email', 'password'],
                properties: {
                  email: { type: 'string', format: 'email', example: 'alex.rivera@acmehealth.com' },
                  password: { type: 'string', format: 'password', example: '••••••••••••' }
                }
              }
            }
          }
        },
        responses: {
          200: { description: 'Authenticated successfully with Bearer Token' },
          401: { description: 'Invalid credentials' }
        }
      }
    },
    '/api/auth/session': {
      get: {
        summary: 'Get active session and user profile',
        tags: ['Authentication'],
        security: [{ bearerAuth: [] }],
        responses: {
          200: { description: 'Current authenticated user profile' },
          401: { description: 'Unauthorized or expired token' }
        }
      }
    },
    '/api/agents': {
      get: {
        summary: 'List all AI voice employees in the fleet',
        tags: ['AI Employees'],
        security: [{ bearerAuth: [] }],
        responses: {
          200: { description: 'Array of AI voice agent models' }
        }
      },
      post: {
        summary: 'Create a new AI voice employee',
        tags: ['AI Employees'],
        security: [{ bearerAuth: [] }],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['name', 'role', 'department'],
                properties: {
                  name: { type: 'string', example: 'Sarah Jenkins' },
                  role: { type: 'string', example: 'Senior Patient Coordinator' },
                  department: { type: 'string', example: 'Patient Intake' },
                  voice: {
                    type: 'object',
                    properties: {
                      provider: { type: 'string', enum: ['Cartesia', 'ElevenLabs', 'Deepgram', 'PlayHT'] },
                      voiceId: { type: 'string' },
                      speed: { type: 'number', minimum: 0.8, maximum: 1.3 },
                      pitch: { type: 'number', minimum: -0.15, maximum: 0.15 }
                    }
                  },
                  language: { type: 'string', example: 'English (US & UK)' },
                  greeting: { type: 'string', example: 'Hello, thank you for calling Summit Dental...' },
                  script: { type: 'string', example: 'You are an autonomous AI voice receptionist...' },
                  transferNumber: { type: 'string', example: '+1 (415) 555-0100' },
                  concurrencyLimit: { type: 'integer', example: 10 }
                }
              }
            }
          }
        },
        responses: {
          201: { description: 'Agent created successfully' }
        }
      }
    },
    '/api/agents/{id}': {
      get: {
        summary: 'Retrieve an individual employee by ID',
        tags: ['AI Employees'],
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Agent profile details' }, 404: { description: 'Agent not found' } }
      },
      put: {
        summary: 'Update full configuration of an individual employee',
        tags: ['AI Employees'],
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Agent configuration updated' } }
      },
      delete: {
        summary: 'Delete an employee from the fleet',
        tags: ['AI Employees'],
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Agent deleted' } }
      }
    },
    '/api/telephony/numbers': {
      get: {
        summary: 'List all purchased virtual phone numbers',
        tags: ['Telephony'],
        responses: { 200: { description: 'Array of virtual numbers' } }
      }
    },
    '/api/telephony/buy': {
      post: {
        summary: 'Provision a new virtual DID from catalog and assign to agent',
        tags: ['Telephony'],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['catalogItem'],
                properties: {
                  catalogItem: { type: 'object' },
                  assignToAgentId: { type: 'string', nullable: true }
                }
              }
            }
          }
        },
        responses: { 201: { description: 'Phone number provisioned' } }
      }
    },
    '/api/calls': {
      get: {
        summary: 'List call records, diarized transcripts, and sentiment logs',
        tags: ['Calls & Transcripts'],
        responses: { 200: { description: 'Call history array' } }
      }
    },
    '/api/calls/outbound': {
      post: {
        summary: 'Initiate autonomous outbound voice call to target phone',
        tags: ['Calls & Transcripts'],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                required: ['targetPhone', 'agentId'],
                properties: {
                  targetPhone: { type: 'string', example: '+1 (555) 019-2834' },
                  callerName: { type: 'string', example: 'Direct Follow-up' },
                  agentId: { type: 'string', example: 'agent-david' }
                }
              }
            }
          }
        },
        responses: { 201: { description: 'Outbound call queued & initiated' } }
      }
    },
    '/api/leads': {
      get: {
        summary: 'Fetch qualified CRM leads from AI calls',
        tags: ['Leads & CRM'],
        responses: { 200: { description: 'Lead pipeline array' } }
      }
    },
    '/api/campaigns': {
      get: {
        summary: 'List automated bulk dialing campaigns',
        tags: ['Campaigns'],
        responses: { 200: { description: 'Campaigns array' } }
      }
    },
    '/api/billing/wallet': {
      get: {
        summary: 'Get real-time minutes balance, rate, and auto-recharge settings',
        tags: ['Billing & Minutes'],
        responses: { 200: { description: 'Wallet status' } }
      }
    },
    '/api/admin/metrics': {
      get: {
        summary: 'System telephony, PSTN gateway, LLM TTFT, and WebRTC diagnostics',
        tags: ['Admin & Diagnostics'],
        responses: { 200: { description: 'Real-time telemetry metrics' } }
      }
    }
  },
  components: {
    securitySchemes: {
      bearerAuth: {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT'
      }
    }
  }
};
