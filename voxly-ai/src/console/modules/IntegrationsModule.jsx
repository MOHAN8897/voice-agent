import React, { useState, useEffect, useMemo } from 'react';
import { 
  Calendar, Database, MessageSquare, Mail, CheckCircle2, 
  ExternalLink, Trash2, RefreshCw, Sliders, ShieldCheck,
  Search, X, Sparkles, Plus, Zap, CreditCard, ShoppingBag, 
  LifeBuoy, Video, GitBranch, Layers, Check, Info, Clock, ArrowRight,
  AlertCircle, Key, Lock, ArrowUpRight, CheckCheck, HelpCircle,
  Activity, ArrowDownRight, Terminal, Globe, ChevronRight, Play,
  BookOpen, Link2, ShieldAlert, Cpu
} from 'lucide-react';
import confetti from 'canvas-confetti';
import Nango from '@nangohq/frontend';
import { SolidCard } from '../ui/SolidCard';
import { api } from '../../services/api';
import { FULL_INTEGRATIONS_CATALOG } from './integrationsCatalog';

// Authentic category colors and glows
export const CATEGORY_COLORS = {
  Scheduling: { bg: 'bg-[#0284C7]/10', text: 'text-[#0284C7]', border: 'border-[#0284C7]/30', glow: 'rgba(2, 132, 199, 0.12)', hex: '#0284C7' },
  CRM: { bg: 'bg-[#EA580C]/10', text: 'text-[#EA580C]', border: 'border-[#EA580C]/30', glow: 'rgba(234, 88, 12, 0.12)', hex: '#EA580C' },
  Communication: { bg: 'bg-[#10B981]/10', text: 'text-[#10B981]', border: 'border-[#10B981]/30', glow: 'rgba(16, 185, 129, 0.12)', hex: '#10B981' },
  Email: { bg: 'bg-[#E11D48]/10', text: 'text-[#E11D48]', border: 'border-[#E11D48]/30', glow: 'rgba(225, 29, 72, 0.12)', hex: '#E11D48' },
  Finance: { bg: 'bg-[#6366F1]/10', text: 'text-[#6366F1]', border: 'border-[#6366F1]/30', glow: 'rgba(99, 102, 241, 0.12)', hex: '#6366F1' },
  Ecommerce: { bg: 'bg-[#84CC16]/10', text: 'text-[#65A30D]', border: 'border-[#84CC16]/30', glow: 'rgba(132, 204, 22, 0.12)', hex: '#84CC16' },
  'E-Commerce': { bg: 'bg-[#84CC16]/10', text: 'text-[#65A30D]', border: 'border-[#84CC16]/30', glow: 'rgba(132, 204, 22, 0.12)', hex: '#84CC16' },
  Support: { bg: 'bg-[#0D9488]/10', text: 'text-[#0D9488]', border: 'border-[#0D9488]/30', glow: 'rgba(13, 148, 136, 0.12)', hex: '#0D9488' },
  Productivity: { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', border: 'border-[#8B5CF6]/30', glow: 'rgba(139, 92, 246, 0.12)', hex: '#8B5CF6' },
  Marketing: { bg: 'bg-[#F59E0B]/10', text: 'text-[#D97706]', border: 'border-[#F59E0B]/30', glow: 'rgba(245, 158, 11, 0.12)', hex: '#F59E0B' },
  Developer: { bg: 'bg-[#475569]/10', text: 'text-[#334155]', border: 'border-[#475569]/30', glow: 'rgba(71, 85, 105, 0.12)', hex: '#475569' },
  Database: { bg: 'bg-[#06B6D4]/10', text: 'text-[#0891B2]', border: 'border-[#06B6D4]/30', glow: 'rgba(6, 182, 212, 0.12)', hex: '#06B6D4' },
};

// Authentic brand accent colors and glows
export const BRAND_COLORS = {
  GOOGLECALENDAR: { bg: 'bg-[#4285F4]/10', text: 'text-[#4285F4]', border: 'border-[#4285F4]/30', glow: 'rgba(66, 133, 244, 0.12)', hex: '#4285F4' },
  CALCOM: { bg: 'bg-[#111111]/10', text: 'text-[#111111]', border: 'border-[#111111]/30', glow: 'rgba(17, 17, 17, 0.12)', hex: '#111111' },
  CALENDLY: { bg: 'bg-[#006BFF]/10', text: 'text-[#006BFF]', border: 'border-[#006BFF]/30', glow: 'rgba(0, 107, 255, 0.12)', hex: '#006BFF' },
  HUBSPOT: { bg: 'bg-[#FF7A59]/10', text: 'text-[#FF7A59]', border: 'border-[#FF7A59]/30', glow: 'rgba(255, 122, 89, 0.12)', hex: '#FF7A59' },
  SALESFORCE: { bg: 'bg-[#00A1E0]/10', text: 'text-[#00A1E0]', border: 'border-[#00A1E0]/30', glow: 'rgba(0, 161, 224, 0.12)', hex: '#00A1E0' },
  PIPEDRIVE: { bg: 'bg-[#121212]/10', text: 'text-[#121212]', border: 'border-[#121212]/30', glow: 'rgba(18, 18, 18, 0.12)', hex: '#121212' },
  ZOHO_CRM: { bg: 'bg-[#E42528]/10', text: 'text-[#E42528]', border: 'border-[#E42528]/30', glow: 'rgba(228, 37, 40, 0.12)', hex: '#E42528' },
  SLACK: { bg: 'bg-[#4A154B]/10', text: 'text-[#4A154B]', border: 'border-[#4A154B]/30', glow: 'rgba(74, 21, 75, 0.12)', hex: '#4A154B' },
  MICROSOFTTEAMS: { bg: 'bg-[#464EB8]/10', text: 'text-[#464EB8]', border: 'border-[#464EB8]/30', glow: 'rgba(70, 78, 184, 0.12)', hex: '#464EB8' },
  GMAIL: { bg: 'bg-[#EA4335]/10', text: 'text-[#EA4335]', border: 'border-[#EA4335]/30', glow: 'rgba(234, 67, 53, 0.12)', hex: '#EA4335' },
  OUTLOOKCALENDAR: { bg: 'bg-[#0078D4]/10', text: 'text-[#0078D4]', border: 'border-[#0078D4]/30', glow: 'rgba(0, 120, 212, 0.12)', hex: '#0078D4' },
  SENDGRID: { bg: 'bg-[#009DD9]/10', text: 'text-[#009DD9]', border: 'border-[#009DD9]/30', glow: 'rgba(0, 157, 217, 0.12)', hex: '#009DD9' },
  WHATSAPP: { bg: 'bg-[#25D366]/10', text: 'text-[#25D366]', border: 'border-[#25D366]/30', glow: 'rgba(37, 211, 102, 0.12)', hex: '#25D366' },
  DISCORD: { bg: 'bg-[#5865F2]/10', text: 'text-[#5865F2]', border: 'border-[#5865F2]/30', glow: 'rgba(88, 101, 242, 0.12)', hex: '#5865F2' },
  STRIPE: { bg: 'bg-[#635BFF]/10', text: 'text-[#635BFF]', border: 'border-[#635BFF]/30', glow: 'rgba(99, 91, 255, 0.12)', hex: '#635BFF' },
  SHOPIFY: { bg: 'bg-[#96BF48]/10', text: 'text-[#96BF48]', border: 'border-[#96BF48]/30', glow: 'rgba(150, 191, 72, 0.12)', hex: '#96BF48' },
  WOOCOMMERCE: { bg: 'bg-[#96588A]/10', text: 'text-[#96588A]', border: 'border-[#96588A]/30', glow: 'rgba(150, 88, 138, 0.12)', hex: '#96588A' },
  ZOOM: { bg: 'bg-[#2D8CFF]/10', text: 'text-[#2D8CFF]', border: 'border-[#2D8CFF]/30', glow: 'rgba(45, 140, 255, 0.12)', hex: '#2D8CFF' },
  NOTION: { bg: 'bg-[#000000]/10', text: 'text-[#000000]', border: 'border-[#000000]/30', glow: 'rgba(0, 0, 0, 0.12)', hex: '#000000' },
  AIRTABLE: { bg: 'bg-[#FCB400]/10', text: 'text-[#FCB400]', border: 'border-[#FCB400]/30', glow: 'rgba(252, 180, 0, 0.12)', hex: '#FCB400' },
  GOOGLESHEETS: { bg: 'bg-[#0F9D58]/10', text: 'text-[#0F9D58]', border: 'border-[#0F9D58]/30', glow: 'rgba(15, 157, 88, 0.12)', hex: '#0F9D58' },
  LINEAR: { bg: 'bg-[#5E6AD2]/10', text: 'text-[#5E6AD2]', border: 'border-[#5E6AD2]/30', glow: 'rgba(94, 106, 210, 0.12)', hex: '#5E6AD2' },
  GITHUB: { bg: 'bg-[#24292F]/10', text: 'text-[#24292F]', border: 'border-[#24292F]/30', glow: 'rgba(36, 41, 47, 0.12)', hex: '#24292F' },
  JIRA: { bg: 'bg-[#0052CC]/10', text: 'text-[#0052CC]', border: 'border-[#0052CC]/30', glow: 'rgba(0, 82, 204, 0.12)', hex: '#0052CC' },
  ZENDESK: { bg: 'bg-[#03363D]/10', text: 'text-[#03363D]', border: 'border-[#03363D]/30', glow: 'rgba(3, 54, 61, 0.12)', hex: '#03363D' },
  FRESHDESK: { bg: 'bg-[#25C9A1]/10', text: 'text-[#25C9A1]', border: 'border-[#25C9A1]/30', glow: 'rgba(37, 201, 161, 0.12)', hex: '#25C9A1' },
  TWILIO_SMS: { bg: 'bg-[#F22F46]/10', text: 'text-[#F22F46]', border: 'border-[#F22F46]/30', glow: 'rgba(242, 47, 70, 0.12)', hex: '#F22F46' },
  SUPABASE: { bg: 'bg-[#3ECF8E]/10', text: 'text-[#3ECF8E]', border: 'border-[#3ECF8E]/30', glow: 'rgba(62, 207, 142, 0.12)', hex: '#3ECF8E' },
  INTERCOM: { bg: 'bg-[#0057FF]/10', text: 'text-[#0057FF]', border: 'border-[#0057FF]/30', glow: 'rgba(0, 87, 255, 0.12)', hex: '#0057FF' },
  ASANA: { bg: 'bg-[#F06A6A]/10', text: 'text-[#F06A6A]', border: 'border-[#F06A6A]/30', glow: 'rgba(240, 106, 106, 0.12)', hex: '#F06A6A' },
  CLICKUP: { bg: 'bg-[#7B68EE]/10', text: 'text-[#7B68EE]', border: 'border-[#7B68EE]/30', glow: 'rgba(123, 104, 238, 0.12)', hex: '#7B68EE' },
  MONDAY: { bg: 'bg-[#FF3D57]/10', text: 'text-[#FF3D57]', border: 'border-[#FF3D57]/30', glow: 'rgba(255, 61, 87, 0.12)', hex: '#FF3D57' },
  TODOIST: { bg: 'bg-[#E44332]/10', text: 'text-[#E44332]', border: 'border-[#E44332]/30', glow: 'rgba(228, 67, 50, 0.12)', hex: '#E44332' },
  MAILCHIMP: { bg: 'bg-[#FFE01B]/20', text: 'text-[#000000]', border: 'border-[#FFE01B]/40', glow: 'rgba(255, 224, 27, 0.12)', hex: '#FFE01B' },
};

// Normalize provider and catalog app keys for resilient multi-tenant matching
export function normalizeAppKey(key) {
  if (!key) return '';
  const clean = String(key).replace(/[-_\s]/g, '').toUpperCase();
  if (clean === 'GOOGLEMAIL' || clean === 'GMAIL') return 'GMAIL';
  if (clean === 'GOOGLECALENDAR') return 'GOOGLECALENDAR';
  if (clean === 'GITHUBGETTINGSTARTED' || clean === 'GITHUB') return 'GITHUB';
  if (clean === 'TWILIO' || clean === 'TWILIOSMS') return 'TWILIO_SMS';
  if (clean === 'CALCOM') return 'CALCOM';
  if (clean === 'CALENDLY') return 'CALENDLY';
  if (clean === 'ZOHO' || clean === 'ZOHOCRM') return 'ZOHO_CRM';
  if (clean === 'GOOGLESHEET' || clean === 'GOOGLESHEETS') return 'GOOGLESHEETS';
  if (clean === 'OUTLOOK' || clean === 'OUTLOOKCALENDAR') return 'OUTLOOKCALENDAR';
  if (clean === 'TEAMS' || clean === 'MICROSOFTTEAMS') return 'MICROSOFTTEAMS';
  return clean;
}

export function IntegrationsModule() {
  const [catalog, setCatalog] = useState(FULL_INTEGRATIONS_CATALOG);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'connected' | 'guide'
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMode, setFilterMode] = useState('all'); // 'all' | 'in_call' | 'post_call' | 'oauth_ready' | 'api_key'
  const [selectedAppModal, setSelectedAppModal] = useState(null);
  const [connectModalApp, setConnectModalApp] = useState(null);
  const [accountAlias, setAccountAlias] = useState('');
  const [authMode, setAuthMode] = useState('oauth'); // 'oauth' | 'apiKey'
  const [manualApiKey, setManualApiKey] = useState('');
  const [isRequestModalOpen, setIsRequestModalOpen] = useState(false);
  const [requestedAppName, setRequestedAppName] = useState('');
  const [requestSubmitted, setRequestSubmitted] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);
  const [popupBlockedUrl, setPopupBlockedUrl] = useState(null);
  const [disconnectApp, setDisconnectApp] = useState(null);

  const fetchIntegrations = async () => {
    try {
      setLoading(true);
      const [connData, catData] = await Promise.all([
        api.request('GET', '/api/integrations').catch(() => ({ items: [] })),
        api.request('GET', '/api/integrations/catalog').catch(() => null)
      ]);
      setConnections(connData?.items || []);
      if (catData?.items && Array.isArray(catData.items) && catData.items.length > 0) {
        const fullMap = new Map(FULL_INTEGRATIONS_CATALOG.map(i => [normalizeAppKey(i.id), i]));
        const merged = catData.items.map(item => {
          const fallback = fullMap.get(normalizeAppKey(item.id)) || {};
          return {
            ...fallback,
            ...item,
            iconName: item.iconName || fallback.iconName || 'Database',
            color: item.color || fallback.color || 'text-brand bg-brand/10',
            actions: (item.actions && item.actions.length > 0) ? item.actions : (fallback.actions || []),
            description: item.description || fallback.description || '',
          };
        });
        setCatalog(merged);
      }
    } catch (err) {
      console.error('Failed to load integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();

    // Listen for OAuth completion message from popup window or Nango Connect UI
    const handleMessage = async (e) => {
      const type = e.data?.type || e.data?.event;
      if (
        type === 'INTEGRATION_CONNECTED' ||
        type === 'connect' ||
        type === 'nango:auth:success' ||
        type === 'nango:connect:success'
      ) {
        const app = (e.data?.app || e.data?.provider || e.data?.payload?.providerConfigKey || connectModalApp?.name || '').toUpperCase();
        triggerConfetti();
        setToastMessage(`Connected ${app || 'integration'} workspace account successfully!`);
        setTimeout(() => setToastMessage(null), 4000);
        setConnecting(null);
        setPopupBlockedUrl(null);
        setConnectModalApp(null);
        await fetchIntegrations();
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [connectModalApp]);

  const triggerConfetti = () => {
    try {
      confetti({
        particleCount: 70,
        spread: 80,
        origin: { y: 0.65 },
        colors: ['#6344E7', '#8369F5', '#10B981', '#3B82F6', '#FF7A59']
      });
    } catch (_) {}
  };

  const getApiKeyInfo = (appId) => {
    switch (appId) {
      case 'STRIPE':
        return {
          label: 'Stripe Secret Key',
          placeholder: 'sk_live_... or sk_test_...',
          help: 'Found in your Stripe Dashboard under Developers > API keys.'
        };
      case 'SHOPIFY':
        return {
          label: 'Shopify Admin API Access Token',
          placeholder: 'shpat_...',
          help: 'Found in Shopify Admin > Settings > Apps > Develop apps.'
        };
      case 'WOOCOMMERCE':
        return {
          label: 'WooCommerce Consumer Key / Secret',
          placeholder: 'ck_...:cs_...',
          help: 'Generated from WooCommerce > Settings > Advanced > REST API.'
        };
      case 'TWILIO_SMS':
        return {
          label: 'Twilio Auth Token',
          placeholder: 'Paste Twilio Auth Token...',
          help: 'Found on your Twilio Console dashboard.'
        };
      case 'WHATSAPP':
        return {
          label: 'WhatsApp Cloud API Access Token',
          placeholder: 'EAAB... (System User Token)',
          help: 'Generated in Meta for Developers under WhatsApp Business.'
        };
      case 'DISCORD':
        return {
          label: 'Discord Bot Token',
          placeholder: 'Paste Discord Bot Token...',
          help: 'Found in Discord Developer Portal > Applications > Bot.'
        };
      case 'SENDGRID':
        return {
          label: 'SendGrid API Key',
          placeholder: 'SG.xxxxxxxx...',
          help: 'Found in SendGrid Settings > API Keys.'
        };
      case 'SUPABASE':
        return {
          label: 'Supabase Service Role Key',
          placeholder: 'eyJh... (Service Role Key)',
          help: 'Found in Supabase Project Settings > API.'
        };
      case 'FRESHDESK':
        return {
          label: 'Freshdesk API Key',
          placeholder: 'Paste Freshdesk API Key...',
          help: 'Found in Freshdesk Profile Settings > Your API Key.'
        };
      default:
        return {
          label: 'API Key or Access Token',
          placeholder: 'Paste API Key or Token...',
          help: 'Encrypted with AES-256 and used exclusively for your agent phone calls.'
        };
    }
  };

  // Prompt the Connect configuration modal
  const openConnectDialog = (app) => {
    setConnectModalApp(app);
    setAccountAlias(`workspace-${app.name.toLowerCase().replace(/[^a-z0-9]/g, '')}`);
    const isApiKey = app.auth_type === 'api_key';
    setAuthMode(isApiKey ? 'apiKey' : 'oauth');
    setManualApiKey('');
  };

  const handleExecuteConnect = async (appId) => {
    if (authMode === 'apiKey' && !manualApiKey.trim()) {
      alert('Please enter an API Key or Token to connect.');
      return;
    }

    // 1. Pre-open window during synchronous user gesture to bypass browser popup blockers
    let popup = null;
    if (authMode === 'oauth') {
      try {
        popup = window.open('about:blank', 'app_oauth', 'width=620,height=720,menubar=no,toolbar=no');
        if (popup && popup.document) {
          popup.document.write(`
            <!DOCTYPE html>
            <html><head><title>Connecting to ${appId}...</title>
            <style>
              body{font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0c0a1a;color:#f8fafc;}
              .loader{width:38px;height:38px;border:3px solid #1e293b;border-top-color:#8369F5;border-radius:50%;animation:s 1s linear infinite;margin:0 auto 16px;}
              @keyframes s{to{transform:rotate(360deg)}}
            </style>
            </head><body><div style="text-align:center"><div class="loader"></div><p style="font-size:14px;color:#cbd5e1;font-weight:600;">Redirecting to ${appId} sign-in...</p><p style="font-size:12px;color:#94a3b8;">Authorize your account to enable voice agent actions</p></div></body></html>
          `);
        }
      } catch (e) {
        console.warn('Popup pre-open notice:', e);
      }
    }

    try {
      setConnecting(appId);
      const data = await api.request('POST', `/api/integrations/${appId}/connect`, {
        base_redirect_uri: `${window.location.origin}/api/integrations/callback`,
        account_identifier: accountAlias.trim() || undefined,
        api_key: authMode === 'apiKey' ? manualApiKey.trim() : undefined,
      });

      // Surface Nango configuration/auth errors clearly to the user
      if (data?.status === 'ERROR' || data?.error) {
        if (popup && !popup.closed) popup.close();
        setConnecting(null);
        if (data?.error === 'nango_credentials_required') {
          setAuthMode('apiKey');
          setToastMessage(`ℹ️ OAuth credentials not yet added in Nango. Switched to direct API Key connection.`);
        } else {
          const msg = data?.message || 'Failed to initiate OAuth. Please check your Nango configuration.';
          setToastMessage(`❌ ${msg}`);
        }
        setTimeout(() => setToastMessage(null), 6000);
        return;
      }

      if (authMode === 'oauth' && data?.redirect_url) {
        if (popup && !popup.closed) {
          // Direct popup window to real Nango Connect OAuth flow
          popup.location.href = data.redirect_url;
          const timer = setInterval(() => {
            if (popup && popup.closed) {
              clearInterval(timer);
              setConnecting(null);
              setConnectModalApp(null);
              triggerConfetti();
              fetchIntegrations();
            }
          }, 1200);
        } else if (data?.session_token) {
          // Popup blocked - fall back to Nango Connect UI in-page modal
          try {
            const nango = new Nango({ connectSessionToken: data.session_token });
            nango.openConnectUI({
              sessionToken: data.session_token,
              onEvent: async (event) => {
                if (event.type === 'connect') {
                  const connId = event.payload?.connectionId || data.connection_id;
                  try {
                    await api.request('POST', `/api/integrations/${appId}/activate`, {
                      connection_id: connId,
                      session_token: data.session_token,
                      account_identifier: accountAlias.trim() || undefined,
                    });
                  } catch (actErr) {
                    console.warn('Backend activation notice:', actErr);
                  }
                  triggerConfetti();
                  setToastMessage(`Connected ${connectModalApp?.name || appId} successfully!`);
                  setTimeout(() => setToastMessage(null), 4000);
                  setConnecting(null);
                  setConnectModalApp(null);
                  fetchIntegrations();
                } else if (event.type === 'close') {
                  setConnecting(null);
                  setConnectModalApp(null);
                  fetchIntegrations();
                }
              },
            });
          } catch (nangoErr) {
            setPopupBlockedUrl({ appId, url: data.redirect_url });
            setConnecting(null);
            setConnectModalApp(null);
          }
        } else {
          // Popup blocked and no session token
          setPopupBlockedUrl({ appId, url: data.redirect_url });
          setConnecting(null);
          setConnectModalApp(null);
        }
      } else {
        // Manual key or direct activation
        if (popup && !popup.closed) popup.close();
        try {
          await api.request('POST', `/api/integrations/${appId}/activate`, {
            connection_id: data?.connection_id || `key_${Date.now()}`,
            account_identifier: accountAlias.trim() || undefined,
          });
        } catch (_) {}
        triggerConfetti();
        setToastMessage(`Successfully authorized ${appId}!`);
        setTimeout(() => setToastMessage(null), 4000);
        setConnecting(null);
        setConnectModalApp(null);
        fetchIntegrations();
      }
    } catch (err) {
      console.error('Failed to initiate secure connection:', err);
      if (popup && !popup.closed) popup.close();
      alert('Failed to initiate secure connection. Please try again.');
      setConnecting(null);
    }
  };

  const promptDisconnect = (app) => {
    setDisconnectApp(app);
  };

  const confirmDisconnect = async () => {
    if (!disconnectApp) return;
    const appId = disconnectApp.id || disconnectApp;
    const appName = disconnectApp.name || appId;
    try {
      await api.request('DELETE', `/api/integrations/${appId}`);
      const cleanTarget = normalizeAppKey(appId);
      setConnections(prev => prev.filter(c => {
        const cleanC = normalizeAppKey(c.app_name || c.id || '');
        return cleanC !== cleanTarget && c.id !== appId;
      }));
      setToastMessage(`Disconnected ${appName}.`);
      setTimeout(() => setToastMessage(null), 3000);
      setDisconnectApp(null);
      await fetchIntegrations();
    } catch (err) {
      console.error('Failed to disconnect integration:', err);
      alert('Failed to disconnect integration.');
    }
  };

  const handleRequestSubmit = (e) => {
    e.preventDefault();
    if (!requestedAppName.trim()) return;
    setRequestSubmitted(true);
    setTimeout(() => {
      setRequestSubmitted(false);
      setIsRequestModalOpen(false);
      setRequestedAppName('');
      triggerConfetti();
      setToastMessage('App request submitted! Our engineering team will review it.');
      setTimeout(() => setToastMessage(null), 4000);
    }, 900);
  };

  const connectedAppKeys = useMemo(() => {
    const set = new Set();
    connections.forEach(c => {
      if (c.status === 'ACTIVE' || !c.status) {
        if (c.app_name) set.add(normalizeAppKey(c.app_name));
        if (c.id) set.add(normalizeAppKey(c.id));
      }
    });
    return set;
  }, [connections]);

  const connectedCount = useMemo(() => {
    return catalog.filter(item => connectedAppKeys.has(normalizeAppKey(item.id))).length;
  }, [catalog, connectedAppKeys]);

  const filteredCatalog = useMemo(() => {
    return catalog.filter(item => {
      const itemKey = normalizeAppKey(item.id);
      const isItemConnected = connectedAppKeys.has(itemKey);

      // 1. Tab Selection Filter: connected vs all
      if (activeTab === 'connected' && !isItemConnected) {
        return false;
      }

      // 2. Text Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = (item.name || '').toLowerCase().includes(q);
        const matchesDesc = (item.description || '').toLowerCase().includes(q);
        const matchesActions = (item.actions || []).some(a => (a || '').toLowerCase().includes(q));
        if (!matchesName && !matchesDesc && !matchesActions) return false;
      }

      // 3. Dropdown Filter: Categorisations of tool uses
      if (filterMode !== 'all') {
        const itemCat = (item.category || '').toLowerCase().trim();
        if (filterMode === 'scheduling' && itemCat !== 'scheduling') return false;
        if (filterMode === 'crm' && itemCat !== 'crm') return false;
        if (filterMode === 'support' && itemCat !== 'support') return false;
        if (filterMode === 'ecommerce' && !['e-commerce', 'ecommerce', 'commerce'].includes(itemCat)) return false;
        if (filterMode === 'communication' && itemCat !== 'communication') return false;
        if (filterMode === 'email' && itemCat !== 'email') return false;
        if (filterMode === 'database' && itemCat !== 'database') return false;
        if (filterMode === 'productivity' && itemCat !== 'productivity') return false;
      }

      return true;
    });
  }, [catalog, searchQuery, filterMode, connectedAppKeys, activeTab]);

  const getIcon = (iconName, className) => {
    switch (iconName) {
      case 'calendar': case 'Calendar': return <Calendar className={className} />;
      case 'database': case 'Database': return <Database className={className} />;
      case 'message-square': case 'MessageSquare': return <MessageSquare className={className} />;
      case 'mail': case 'Mail': return <Mail className={className} />;
      case 'credit-card': case 'CreditCard': return <CreditCard className={className} />;
      case 'shopping-bag': case 'ShoppingBag': return <ShoppingBag className={className} />;
      case 'life-buoy': case 'LifeBuoy': return <LifeBuoy className={className} />;
      case 'video': case 'Video': return <Video className={className} />;
      case 'git-branch': case 'GitBranch': return <GitBranch className={className} />;
      case 'layers': case 'Layers': return <Layers className={className} />;
      case 'zap': case 'Zap': return <Zap className={className} />;
      case 'sliders': case 'Sliders': return <Sliders className={className} />;
      default: return <Database className={className} />;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-20 font-sans">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#0c0a1a] border border-brand/40 text-white px-4 py-3 rounded-2xl shadow-craft-lg flex items-center space-x-3 text-xs font-semibold animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center flex-shrink-0 animate-radar">
            <CheckCheck className="w-3.5 h-3.5" />
          </div>
          <span className="tracking-wide">{toastMessage}</span>
        </div>
      )}

      {/* Popup Blocked Fallback Modal */}
      {popupBlockedUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 max-w-md w-full shadow-craft-lg space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-center space-x-3 text-amber-500">
              <div className="w-10 h-10 rounded-2xl bg-amber-50 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h3 className="font-extrabold text-[#0F0E17] text-sm">Action Required: Authorize Account</h3>
                <p className="text-[11px] text-[#524E5E]">Browser popup blocker intercepted authorization</p>
              </div>
            </div>
            <p className="text-xs text-[#524E5E] leading-relaxed">
              Your browser prevented the automatic sign-in window. Click below to open <strong>{popupBlockedUrl.appId}</strong>'s sign-in screen securely:
            </p>
            <div className="flex justify-end space-x-2.5 pt-2 border-t border-[#E4E2EB]">
              <button 
                onClick={() => setPopupBlockedUrl(null)}
                className="px-3.5 py-2 text-xs text-[#524E5E] hover:text-[#0F0E17] font-semibold transition-colors"
              >
                Cancel
              </button>
              <a 
                href={popupBlockedUrl.url} 
                target="_blank" 
                rel="noreferrer"
                data-testid="authorize-popup-btn"
                onClick={() => {
                  setTimeout(() => {
                    setPopupBlockedUrl(null);
                    triggerConfetti();
                    fetchIntegrations();
                  }, 1500);
                }}
                className="px-4 py-2 bg-brand hover:bg-brand-hover text-white text-xs font-bold rounded-xl flex items-center space-x-1.5 shadow-craft-xs transition-all hover:scale-105 active:scale-95"
              >
                <span>Authorize & Sign In</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Premium Hero Header with Fluid Aurora Ambient Lighting */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#0c0a1a] via-[#141226] to-[#1e173b] text-white p-6 sm:p-8 shadow-craft-lg border border-white/10">
        {/* Subtle animated aurora mesh */}
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-gradient-to-br from-brand/25 to-indigo-600/20 rounded-full blur-3xl pointer-events-none -mr-32 -mt-32 animate-aurora"></div>
        <div className="absolute bottom-0 left-1/4 w-80 h-80 bg-brand-accent/15 rounded-full blur-2xl pointer-events-none -mb-28"></div>

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2.5 max-w-2xl">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-md border border-white/15 text-[11px] font-semibold text-brand-light">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-radar"></span>
              <span className="font-bold tracking-wide">Enterprise Voice Tooling</span>
              <span className="w-1 h-1 rounded-full bg-white/40"></span>
              <span className="text-white/80">{catalog.length}+ Integrations Available</span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white leading-tight">
              App Integrations & Voice Tools
            </h1>
            <p className="text-xs sm:text-sm text-[#D1CFDB] leading-relaxed">
              Equip your AI voice agents with sub-second in-call tool dispatching and post-call automations. Connect calendar, CRM, e-commerce, messaging, and database services securely.
            </p>

            {/* Live Telemetry Chips */}
            <div className="flex items-center space-x-4 pt-1 text-xs flex-wrap gap-y-2">
              <div className="flex items-center space-x-1.5 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                <span className="font-bold">{connections.length} Connected</span>
              </div>
              <span className="text-white/20">•</span>
              <div className="flex items-center space-x-1.5 text-[#D1CFDB]">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Live In-Call (&lt;1.5s SLA)</span>
              </div>
              <span className="text-white/20">•</span>
              <div className="flex items-center space-x-1.5 text-[#D1CFDB]">
                <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
                <span>AES-256 Vault Encrypted</span>
              </div>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center space-x-3 flex-shrink-0">
            <button
              onClick={() => setIsRequestModalOpen(true)}
              data-testid="request-app-btn"
              className="px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 text-xs font-bold text-white transition-all duration-200 flex items-center space-x-2 backdrop-blur-md hover:scale-105 active:scale-95 shadow-craft-xs"
            >
              <Plus className="w-4 h-4 text-brand-accent" />
              <span>Request Custom Integration</span>
            </button>
            <button
              onClick={fetchIntegrations}
              disabled={loading}
              className="p-2.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 text-white/80 hover:text-white transition-all backdrop-blur-md hover:scale-105 active:scale-95"
              title="Refresh Catalog"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* View Mode Navigation Tabs: 3 clean tabs */}
        <div className="relative z-10 flex items-center space-x-2 mt-6 pt-5 border-t border-white/10 overflow-x-auto scrollbar-none">
          <button
            onClick={() => setActiveTab('all')}
            data-testid="tab-all-integrations"
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200 flex items-center space-x-2 ${
              activeTab === 'all'
                ? 'bg-white text-[#0F0E17] shadow-craft-sm scale-[1.02]'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>All Integrations</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${activeTab === 'all' ? 'bg-[#0F0E17]/10 text-[#0F0E17]' : 'bg-white/20 text-white'}`}>
              {catalog.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('connected')}
            data-testid="tab-connected"
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200 flex items-center space-x-2 ${
              activeTab === 'connected'
                ? 'bg-white text-[#0F0E17] shadow-craft-sm scale-[1.02]'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>Connected Integrations</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${activeTab === 'connected' ? 'bg-emerald-100 text-emerald-800' : 'bg-emerald-500/20 text-emerald-300'}`}>
              {connectedCount}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('guide')}
            data-testid="tab-guide"
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200 flex items-center space-x-2 ${
              activeTab === 'guide'
                ? 'bg-white text-[#0F0E17] shadow-craft-sm scale-[1.02]'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            <HelpCircle className="w-3.5 h-3.5 text-brand-accent" />
            <span>How Connections Work</span>
          </button>
        </div>
      </div>

      {/* TAB 1 & 2: ALL & CONNECTED INTEGRATIONS */}
      {activeTab !== 'guide' && (
        <>
          {/* Unified Search & Dropdown Filter Toolbar */}
          <div className="bg-white border border-[#E4E2EB] rounded-2xl p-4 shadow-craft-xs flex flex-col md:flex-row md:items-center justify-between gap-3.5">
            {/* Search Input */}
            <div className="relative flex-1 max-w-xl group">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#524E5E] group-focus-within:text-brand transition-colors" />
              <input
                type="text"
                data-testid="integration-search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={
                  activeTab === 'connected'
                    ? 'Search connected integrations (e.g. Google Calendar, Slack, HubSpot)...'
                    : 'Search all available integrations and voice tools (e.g. Calendly, Stripe, Shopify)...'
                }
                className="w-full pl-10 pr-9 py-2.5 sm:py-2 min-h-[42px] sm:min-h-[36px] text-base sm:text-xs bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl focus:outline-none focus:border-brand focus:ring-4 focus:ring-brand/10 text-[#0F0E17] placeholder:text-[#524E5E] transition-all"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#524E5E] hover:text-[#0F0E17] p-1 min-w-[32px] min-h-[32px] flex items-center justify-center rounded-full hover:bg-[#F0EEF6] transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Controls: Filter Dropdown & Counter */}
            <div className="flex items-center space-x-3 flex-wrap sm:flex-nowrap">
              <div className="flex items-center space-x-2 w-full sm:w-auto">
                <Sliders className="w-3.5 h-3.5 text-[#524E5E] hidden sm:block" />
                <select
                  data-testid="integration-filter-select"
                  value={filterMode}
                  onChange={(e) => setFilterMode(e.target.value)}
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-semibold text-[#0F0E17] focus:outline-none focus:border-brand focus:ring-4 focus:ring-brand/10 cursor-pointer min-h-[36px]"
                >
                  <option value="all">All Tool Uses (All {catalog.length} Integrations)</option>
                  <option value="scheduling">📅 Calendar & Scheduling (Bookings & Slots)</option>
                  <option value="crm">💼 CRM & Sales Leads (Contacts & Pipeline)</option>
                  <option value="support">🎧 Customer Support & Helpdesk (Tickets & SLA)</option>
                  <option value="ecommerce">🛍️ E-Commerce & Payments (Orders & Billing)</option>
                  <option value="communication">💬 Team Communication & Messaging (Slack, SMS)</option>
                  <option value="email">✉️ Email & Follow-Ups (Gmail, Campaigns)</option>
                  <option value="database">📊 Databases & Spreadsheets (Airtable, Sheets)</option>
                  <option value="productivity">📋 Task & Project Management (Asana, Monday)</option>
                </select>
              </div>

              <div className="text-[11px] font-bold text-[#524E5E] bg-[#FAF9FD] border border-[#E4E2EB] px-3 py-2 rounded-xl whitespace-nowrap min-h-[36px] flex items-center">
                <span>{filteredCatalog.length} {filteredCatalog.length === 1 ? 'tool' : 'tools'}</span>
              </div>
            </div>
          </div>

          {/* Full Grid: Displays all available integrations immediately */}
          {filteredCatalog.length === 0 ? (
            <div className="text-center py-16 border border-dashed border-[#E4E2EB] rounded-3xl bg-white p-8 shadow-craft-xs">
              {activeTab === 'connected' && !searchQuery ? (
                <div>
                  <div className="w-14 h-14 rounded-2xl bg-brand/10 text-brand flex items-center justify-center mx-auto mb-4">
                    <Layers className="w-7 h-7" />
                  </div>
                  <h3 className="text-base font-extrabold text-[#0F0E17]">No Integrations Connected Yet</h3>
                  <p className="text-xs text-[#524E5E] mt-1.5 max-w-md mx-auto leading-relaxed">
                    Connect Google Calendar, Slack, HubSpot, or any voice tools to equip your AI voice agent with real-time in-call actions.
                  </p>
                  <div className="mt-5 flex items-center justify-center space-x-3">
                    <button
                      onClick={() => setActiveTab('all')}
                      className="px-5 py-2.5 bg-brand hover:bg-brand-hover text-white text-xs font-bold rounded-xl shadow-craft-xs flex items-center space-x-2 transition-all hover:scale-105 active:scale-95"
                    >
                      <Layers className="w-4 h-4" />
                      <span>Browse All {catalog.length} Integrations</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="w-12 h-12 rounded-2xl bg-[#F0EEF6] flex items-center justify-center mx-auto mb-3 text-brand">
                    <Search className="w-6 h-6 text-[#524E5E]" />
                  </div>
                  <h3 className="text-sm font-bold text-[#0F0E17]">No integrations match criteria</h3>
                  <p className="text-xs text-[#524E5E] mt-1 max-w-sm mx-auto">
                    {searchQuery
                      ? `No voice tools match "${searchQuery}". Try a different keyword.`
                      : 'No voice tools match the selected filter.'}
                  </p>
                  <div className="flex justify-center space-x-3 mt-4">
                    <button
                      onClick={() => { setSearchQuery(''); setFilterMode('all'); }}
                      className="px-4 py-2 text-xs font-semibold text-brand hover:underline"
                    >
                      Reset Filters
                    </button>
                    <button
                      onClick={() => setIsRequestModalOpen(true)}
                      className="px-4 py-2 bg-[#0F0E17] text-white text-xs font-bold rounded-xl shadow-craft-xs"
                    >
                      Request Integration
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3.5">
              {filteredCatalog.map(app => {
                const isConnected = connectedAppKeys.has(normalizeAppKey(app.id));
                const isConnectingThis = connecting === app.id;
                const brandColor = BRAND_COLORS[app.id] || CATEGORY_COLORS[app.category] || { 
                  bg: 'bg-brand/10', 
                  text: 'text-brand', 
                  border: 'border-brand/20',
                  glow: 'rgba(99, 68, 231, 0.12)'
                };

                return (
                  <SolidCard 
                    key={app.id} 
                    className={`p-4 flex flex-col justify-between transition-all duration-300 hover:shadow-craft-md hover:-translate-y-1 group relative overflow-hidden bg-white animate-card-entrance ${
                      isConnected ? 'border-emerald-500/40 ring-1 ring-emerald-500/20' : 'border-[#E4E2EB]'
                    }`}
                  >
                    <div>
                      {/* Top Bar: Icon, Name, Category & Status */}
                      <div className="flex items-start justify-between gap-2.5 mb-2.5">
                        <div className="flex items-center space-x-2.5 min-w-0">
                          <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-transform group-hover:scale-110 ${brandColor.bg} ${brandColor.text}`}>
                            {getIcon(app.iconName, "w-4 h-4")}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center space-x-1.5">
                              <h3 className="text-xs font-bold text-[#0F0E17] truncate group-hover:text-brand transition-colors">
                                {app.name}
                              </h3>
                            </div>
                            <div className="flex items-center space-x-1.5 text-[10px] text-[#524E5E] mt-0.5 flex-wrap gap-y-1">
                              <span className="px-1.5 py-0.2 rounded-md font-bold bg-[#F0EEF6] text-[#0F0E17] border border-[#E4E2EB]">
                                {app.category}
                              </span>
                              <span className="truncate font-medium">{app.timing === 'in_call' ? 'Live In-Call' : 'Post-Call'}</span>
                              {app.auth_type === 'oauth' ? (
                                <span className="px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200" title="1-Click OAuth 2.0 Sign-In (Zero API Key needed)">
                                  ⚡ 1-Click OAuth
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-purple-50 text-purple-700 border border-purple-200" title="Direct API Key / Token Authentication">
                                  🔑 Direct API Key
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Status Badge */}
                        {isConnected ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex-shrink-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1 animate-pulse"></span>
                            Active
                          </span>
                        ) : (
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-medium border flex-shrink-0 ${
                            app.timing === 'in_call' 
                              ? 'bg-amber-50 border-amber-200 text-amber-700' 
                              : 'bg-[#FAF9FD] border-[#E4E2EB] text-[#524E5E]'
                          }`}>
                            {app.timing === 'in_call' ? '⚡ Live' : '🕒 Async'}
                          </span>
                        )}
                      </div>

                      {/* Concise Description */}
                      <p className="text-[11px] text-[#524E5E] line-clamp-2 leading-relaxed mb-3">
                        {app.description}
                      </p>

                      {/* Top Action Tags */}
                      {app.actions && app.actions.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-3">
                          {app.actions.slice(0, 2).map((act, i) => (
                            <span key={i} className="text-[10px] bg-[#FAF9FD] border border-[#E4E2EB] px-1.5 py-0.5 rounded-md text-[#524E5E] font-medium truncate max-w-[140px]">
                              {act}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Card Footer: Action Drawer Link & Connect / Disconnect Button */}
                    <div className="pt-2.5 border-t border-[#E4E2EB]/70 flex items-center justify-between gap-2">
                      <button
                        onClick={() => setSelectedAppModal(app)}
                        className="text-[11px] text-[#524E5E] hover:text-brand font-semibold flex items-center space-x-1 group/btn transition-colors"
                      >
                        <span>{app.actions?.length || 2} actions</span>
                        <ArrowRight className="w-3 h-3 group-hover/btn:translate-x-0.5 transition-transform" />
                      </button>

                      <div>
                        {isConnected ? (
                          <button
                            onClick={() => promptDisconnect(app)}
                            data-testid={`disconnect-btn-${app.id.toLowerCase()}`}
                            className="px-2.5 py-1 text-[11px] font-semibold text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-lg transition-colors border border-transparent hover:border-rose-200"
                            title="Disconnect Integration"
                          >
                            Disconnect
                          </button>
                        ) : (
                          <button
                            onClick={() => openConnectDialog(app)}
                            disabled={isConnectingThis}
                            data-testid={`connect-btn-${app.id.toLowerCase()}`}
                            className="px-3.5 py-1.5 bg-[#0F0E17] hover:bg-brand text-white text-[11px] font-bold rounded-xl shadow-craft-xs hover:shadow-craft-sm transition-all duration-200 flex items-center space-x-1 hover:scale-105 active:scale-95"
                          >
                            {isConnectingThis ? (
                              <>
                                <RefreshCw className="w-3 h-3 animate-spin" />
                                <span>Connecting...</span>
                              </>
                            ) : (
                              <span>Connect</span>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </SolidCard>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* TAB 3: HOW CONNECTIONS WORK & AUTHORIZATION ARCHITECTURE */}
      {activeTab === 'guide' && (
        <div className="space-y-6 animate-in fade-in duration-300">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 sm:p-8 shadow-craft-xs space-y-6">
            <div className="space-y-2">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-brand/10 text-brand text-xs font-bold">
                <ShieldCheck className="w-4 h-4 text-brand" />
                <span>Zero-Trust Enterprise Architecture</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-extrabold text-[#0F0E17]">
                How App Connections & Tenant Sign-In Work
              </h2>
              <p className="text-xs sm:text-sm text-[#524E5E] leading-relaxed max-w-3xl">
                Every tool integration links your voice agents directly to your third-party SaaS accounts. Here is exactly how authorization, credentials, and live phone call tool calls operate.
              </p>
            </div>

            {/* Visual Step-by-Step Flow */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div className="p-5 rounded-2xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3 relative overflow-hidden">
                <div className="w-8 h-8 rounded-xl bg-brand/10 text-brand font-bold text-xs flex items-center justify-center">
                  1
                </div>
                <h3 className="font-bold text-sm text-[#0F0E17]">Personal / Workspace Sign-In</h3>
                <p className="text-xs text-[#524E5E] leading-relaxed">
                  In live production, clicking <strong>Connect</strong> opens the provider's official OAuth sign-in window (e.g., <em>Google, HubSpot, Slack</em>). You log in to your account and approve the requested calendar or CRM scopes.
                </p>
                <div className="text-[11px] text-brand font-semibold flex items-center space-x-1">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Passwords never touch Voxly</span>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3 relative overflow-hidden">
                <div className="w-8 h-8 rounded-xl bg-emerald-500/10 text-emerald-600 font-bold text-xs flex items-center justify-center">
                  2
                </div>
                <h3 className="font-bold text-sm text-[#0F0E17]">Encrypted Tenant Vault</h3>
                <p className="text-xs text-[#524E5E] leading-relaxed">
                  Once authorized, the OAuth token is bound exclusively to your unique tenant ID and encrypted at rest with <strong>AES-256 GCM</strong>. No other tenant or agent can access your account.
                </p>
                <div className="text-[11px] text-emerald-600 font-semibold flex items-center space-x-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Cryptographically Isolated</span>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3 relative overflow-hidden">
                <div className="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-600 font-bold text-xs flex items-center justify-center">
                  3
                </div>
                <h3 className="font-bold text-sm text-[#0F0E17]">Sub-Second In-Call Dispatch</h3>
                <p className="text-xs text-[#524E5E] leading-relaxed">
                  When a caller asks to schedule an appointment during a phone call, the voice AI securely queries your calendar and reserves the slot in <strong>&lt;1.5 seconds</strong> without human intervention.
                </p>
                <div className="text-[11px] text-amber-600 font-semibold flex items-center space-x-1">
                  <Zap className="w-3.5 h-3.5" />
                  <span>Real-time voice SLA</span>
                </div>
              </div>
            </div>

            {/* Operating Modes Callout */}
            <div className="p-5 rounded-2xl bg-[#0c0a1a] text-white border border-white/10 space-y-3">
              <div className="flex items-center space-x-2 text-amber-400 font-bold text-xs">
                <Info className="w-4 h-4" />
                <span>Notice on Development Sandbox vs. Production Mode</span>
              </div>
              <p className="text-xs text-[#D1CFDB] leading-relaxed">
                In this local development sandbox environment, instant connection simulation is active when third-party provider keys are in test mode. This enables testing full voice call agentic loops without requiring 170+ paid SaaS enterprise accounts. In live production environments, clicking Connect will always direct the tenant to sign into their official SaaS provider login.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Connect Modal (Explains OAuth Sign-In vs API Key) */}
      {connectModalApp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 sm:p-7 max-w-lg w-full max-h-[90vh] overflow-y-auto shadow-craft-lg space-y-5 animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className={`w-11 h-11 rounded-2xl flex items-center justify-center ${BRAND_COLORS[connectModalApp.id]?.bg || 'bg-brand/10'} ${BRAND_COLORS[connectModalApp.id]?.text || 'text-brand'}`}>
                  {getIcon(connectModalApp.iconName, "w-6 h-6")}
                </div>
                <div>
                  <h3 className="font-extrabold text-[#0F0E17] text-base">Connect {connectModalApp.name}</h3>
                  <div className="flex items-center space-x-1.5 text-xs text-[#524E5E] mt-0.5">
                    <span>{connectModalApp.category}</span>
                    <span>•</span>
                    <span className="font-semibold text-brand">Voice Agent Enabled</span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setConnectModalApp(null)}
                className="text-[#524E5E] hover:text-[#0F0E17] p-1.5 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-xl hover:bg-[#F0EEF6] transition-colors"
                aria-label="Close connect dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Authorization Module: Dedicated per Integration (No confusing tab switcher or unused API space) */}
            <div className="space-y-3">
              {connectModalApp.auth_type === 'oauth' ? (
                <div className="space-y-3">
                  <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 space-y-2">
                    <div className="flex items-center space-x-2 text-xs font-bold text-emerald-800">
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      <span>1-Click OAuth 2.0 Sign-In</span>
                    </div>
                    <p className="text-xs text-emerald-950/80 leading-relaxed">
                      Clicking continue will open <strong>{connectModalApp.name}</strong>'s official sign-in page. You approve permissions with your existing workspace account—zero manual API keys or secrets required.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="p-4 rounded-2xl bg-brand/10 border border-brand/20 space-y-2">
                    <div className="flex items-center space-x-2 text-xs font-bold text-brand">
                      <Key className="w-4 h-4 text-brand" />
                      <span>Direct API Key Connection</span>
                    </div>
                    <p className="text-xs text-[#524E5E] leading-relaxed">
                      <strong>{connectModalApp.name}</strong> connects directly via your workspace API credentials. Enter your token below to enable in-call voice actions.
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-xs font-bold text-[#0F0E17]">
                      {getApiKeyInfo(connectModalApp.id).label}
                    </label>
                    <input
                      type="password"
                      value={manualApiKey}
                      onChange={(e) => setManualApiKey(e.target.value)}
                      placeholder={getApiKeyInfo(connectModalApp.id).placeholder}
                      className="w-full px-3.5 py-2.5 min-h-[42px] sm:min-h-[36px] text-base sm:text-xs bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl focus:outline-none focus:border-brand focus:ring-4 focus:ring-brand/10 text-[#0F0E17]"
                    />
                    <p className="text-[11px] text-[#524E5E]">
                      {getApiKeyInfo(connectModalApp.id).help}
                    </p>
                  </div>
                </div>
              )}

              {/* Account Alias Input */}
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-[#0F0E17]">
                  Account Label / Alias
                </label>
                <input
                  type="text"
                  value={accountAlias}
                  onChange={(e) => setAccountAlias(e.target.value)}
                  placeholder="e.g. sales-team@company.com or Primary CRM"
                  className="w-full px-3.5 py-2.5 min-h-[42px] sm:min-h-[36px] text-base sm:text-xs bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl focus:outline-none focus:border-brand focus:ring-4 focus:ring-brand/10 text-[#0F0E17]"
                />
              </div>

              {/* Scopes Preview */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-bold text-[#0F0E17] uppercase tracking-wider">
                  Granted Voice Permissions:
                </span>
                <div className="space-y-1">
                  {(connectModalApp.actions || ['Check Status', 'Execute Action']).map((action, i) => (
                    <div key={i} className="flex items-center space-x-2 text-xs text-[#524E5E]">
                      <Check className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                      <span>{action}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="pt-3 border-t border-[#E4E2EB] flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <span className="text-[11px] text-[#524E5E] flex items-center space-x-1 justify-center sm:justify-start">
                <Lock className="w-3 h-3 text-emerald-600" />
                <span>Encrypted • Revocable anytime</span>
              </span>

              <div className="flex items-center space-x-2.5">
                <button
                  type="button"
                  onClick={() => setConnectModalApp(null)}
                  className="flex-1 sm:flex-initial px-3.5 py-2 min-h-[40px] text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  data-testid="confirm-connect-btn"
                  onClick={() => handleExecuteConnect(connectModalApp.id)}
                  disabled={connecting === connectModalApp.id}
                  className="flex-1 sm:flex-initial px-5 py-2 min-h-[40px] bg-brand hover:bg-brand-hover text-white text-xs font-bold rounded-xl shadow-craft-xs flex items-center justify-center space-x-2 transition-all hover:scale-105 active:scale-95"
                >
                  {connecting === connectModalApp.id ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Opening Sign-In...</span>
                    </>
                  ) : (
                    <>
                      <span>{authMode === 'oauth' ? `Sign In to ${connectModalApp.name}` : 'Save & Connect'}</span>
                      <ArrowUpRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action Preview Modal */}
      {selectedAppModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 max-w-md w-full shadow-craft-lg space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center ${BRAND_COLORS[selectedAppModal.id]?.bg || 'bg-brand/10'} ${BRAND_COLORS[selectedAppModal.id]?.text || 'text-brand'}`}>
                  {getIcon(selectedAppModal.iconName, "w-5 h-5")}
                </div>
                <div>
                  <h3 className="font-extrabold text-[#0F0E17] text-sm">{selectedAppModal.name}</h3>
                  <div className="flex items-center space-x-1.5 text-xs text-[#524E5E]">
                    <span className="font-semibold text-emerald-600">{selectedAppModal.oauth_ready ? '⚡ 1-Click OAuth' : '🔑 API Key Auth'}</span>
                    <span>•</span>
                    <span className={selectedAppModal.timing === 'in_call' ? 'text-amber-600 font-bold' : 'text-indigo-600 font-bold'}>
                      {selectedAppModal.timing_label || (selectedAppModal.timing === 'in_call' ? 'Live In-Call (<1.5s)' : 'Async Post-Call')}
                    </span>
                  </div>
                </div>
              </div>
              <button 
                data-testid="action-modal-close-btn"
                onClick={() => setSelectedAppModal(null)}
                className="text-[#524E5E] hover:text-[#0F0E17] p-1 rounded-xl hover:bg-[#F0EEF6]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-[#524E5E] leading-relaxed">
              {selectedAppModal.description}
            </p>

            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                Configured Voice Actions
              </h4>
              <div className="space-y-1.5">
                {(selectedAppModal.actions || ['Check Status', 'Execute Action']).map((action, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-xs">
                    <span className="font-semibold text-[#0F0E17]">{action}</span>
                    <span className="text-[10px] text-[#524E5E] bg-[#F0EEF6] px-2 py-0.5 rounded-full font-medium">
                      {selectedAppModal.timing === 'in_call' ? 'Sub-second Voice' : 'Durable Task'}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2 border-t border-[#E4E2EB] flex justify-end">
              <button
                onClick={() => setSelectedAppModal(null)}
                className="px-4 py-2 bg-[#FAF9FD] hover:bg-[#F0EEF6] text-[#0F0E17] text-xs font-bold rounded-xl border border-[#E4E2EB] transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Request App Modal */}
      {isRequestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 max-w-md w-full shadow-craft-lg space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between">
              <h3 className="font-extrabold text-[#0F0E17] text-sm flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-brand" />
                <span>Request Custom Integration</span>
              </h3>
              <button 
                onClick={() => setIsRequestModalOpen(false)}
                className="text-[#524E5E] hover:text-[#0F0E17] p-1 rounded-xl hover:bg-[#F0EEF6]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-[#524E5E] leading-relaxed">
              Need to connect a private ERP, internal database, or unlisted SaaS tool? Tell us what you need and our platform team will prioritize it.
            </p>

            <form onSubmit={handleRequestSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  App or Tool Name
                </label>
                <input
                  type="text"
                  required
                  value={requestedAppName}
                  onChange={(e) => setRequestedAppName(e.target.value)}
                  placeholder="e.g. NetSuite, Workday, Custom CRM..."
                  className="w-full px-3.5 py-2 text-xs bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl focus:outline-none focus:border-brand focus:ring-4 focus:ring-brand/10 text-[#0F0E17]"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setIsRequestModalOpen(false)}
                  className="px-3.5 py-2 text-xs text-[#524E5E] hover:text-[#0F0E17] font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={requestSubmitted}
                  className="px-4 py-2 bg-brand hover:bg-brand-hover text-white text-xs font-bold rounded-xl flex items-center space-x-1.5 shadow-craft-xs"
                >
                  {requestSubmitted ? (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>Submitted!</span>
                    </>
                  ) : (
                    <span>Submit Request</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Disconnect Confirmation Modal */}
      {disconnectApp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-white border border-[#E4E2EB] rounded-3xl p-6 max-w-sm w-full shadow-craft-lg space-y-4 animate-in zoom-in-95 duration-200">
            <div className="flex items-center space-x-3 text-rose-600">
              <div className="w-10 h-10 rounded-2xl bg-rose-50 flex items-center justify-center flex-shrink-0">
                <Trash2 className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <h3 className="font-extrabold text-[#0F0E17] text-sm">Disconnect {disconnectApp.name || disconnectApp.id}?</h3>
                <p className="text-[11px] text-[#524E5E]">Revoke voice agent access</p>
              </div>
            </div>
            <p className="text-xs text-[#524E5E] leading-relaxed">
              Are you sure you want to disconnect this integration? Active voice agents will no longer have access to this tool during calls.
            </p>
            <div className="flex justify-end space-x-2 pt-2 border-t border-[#E4E2EB]">
              <button
                type="button"
                onClick={() => setDisconnectApp(null)}
                className="px-3.5 py-2 text-xs text-[#524E5E] hover:text-[#0F0E17] font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="confirm-disconnect-btn"
                onClick={confirmDisconnect}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-craft-xs transition-colors"
              >
                Disconnect
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
