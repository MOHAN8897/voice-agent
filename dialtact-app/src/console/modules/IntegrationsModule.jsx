import React, { useState, useEffect, useMemo, useRef } from 'react';
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
import { SolidCard, Section } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { PageHeader } from '../ui/PageHeader';
import { Badge } from '../ui/StatusBadge';
import { EmptyState } from '../ui/EmptyState';
import { api } from '../../services/api';
import { FULL_INTEGRATIONS_CATALOG } from './integrationsCatalog';

// Third-party category and brand colours for app icon tiles only (intentionally not
// design tokens: they identify the vendor). Status never uses these.
export const CATEGORY_COLORS = {
  Scheduling: { bg: 'bg-[#0284C7]/10', text: 'text-[#0284C7]', border: 'border-[#0284C7]/30', glow: 'rgba(2, 132, 199, 0.12)', hex: '#0284C7' },
  CRM: { bg: 'bg-[#EA580C]/10', text: 'text-[#EA580C]', border: 'border-[#EA580C]/30', glow: 'rgba(234, 88, 12, 0.12)', hex: '#EA580C' },
  Communication: { bg: 'bg-success/10', text: 'text-success-fg', border: 'border-success/30', glow: 'rgba(16, 185, 129, 0.12)', hex: '#10B981' },
  Email: { bg: 'bg-[#E11D48]/10', text: 'text-[#E11D48]', border: 'border-[#E11D48]/30', glow: 'rgba(225, 29, 72, 0.12)', hex: '#E11D48' },
  Finance: { bg: 'bg-[#6366F1]/10', text: 'text-[#6366F1]', border: 'border-[#6366F1]/30', glow: 'rgba(99, 102, 241, 0.12)', hex: '#6366F1' },
  Ecommerce: { bg: 'bg-[#84CC16]/10', text: 'text-[#65A30D]', border: 'border-[#84CC16]/30', glow: 'rgba(132, 204, 22, 0.12)', hex: '#84CC16' },
  'E-Commerce': { bg: 'bg-[#84CC16]/10', text: 'text-[#65A30D]', border: 'border-[#84CC16]/30', glow: 'rgba(132, 204, 22, 0.12)', hex: '#84CC16' },
  Support: { bg: 'bg-[#0D9488]/10', text: 'text-[#0D9488]', border: 'border-[#0D9488]/30', glow: 'rgba(13, 148, 136, 0.12)', hex: '#0D9488' },
  Productivity: { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]', border: 'border-[#8B5CF6]/30', glow: 'rgba(139, 92, 246, 0.12)', hex: '#8B5CF6' },
  Marketing: { bg: 'bg-warning/10', text: 'text-warning-fg', border: 'border-warning/30', glow: 'rgba(245, 158, 11, 0.12)', hex: '#F59E0B' },
  Developer: { bg: 'bg-[#475569]/10', text: 'text-[#334155]', border: 'border-[#475569]/30', glow: 'rgba(71, 85, 105, 0.12)', hex: '#475569' },
  Database: { bg: 'bg-[#06B6D4]/10', text: 'text-[#0891B2]', border: 'border-[#06B6D4]/30', glow: 'rgba(6, 182, 212, 0.12)', hex: '#06B6D4' },
};

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
const FALLBACK_COLOR = { bg: 'bg-accent-soft', text: 'text-accent-fg', border: 'border-accent-soft', glow: 'rgba(99, 68, 231, 0.12)' };

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

// The server explains why a connection form cannot open; a generic line hides the fix.
export function connectFailureMessage(error) {
  const status = error?.status;
  if (status === 429) return 'Too many connection attempts. Wait a few minutes and try again.';
  if (status === 403) return 'Your role cannot connect integrations. Ask a workspace owner or admin.';
  if (status === 401) return 'Your session expired. Sign in again to connect.';
  if (status === 0) return 'Could not reach the server. Check your connection and retry.';
  if ([400, 404, 503].includes(status) && error?.message && !/^HTTP \d+$/.test(error.message)) {
    return error.message;
  }
  return 'Could not open the secure connection form. Please retry or contact your administrator.';
}

export function IntegrationsModule() {
  const [catalog, setCatalog] = useState([]);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'connected' | 'guide'
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMode, setFilterMode] = useState('all'); // 'all' | 'in_call' | 'post_call' | 'oauth_ready' | 'api_key'
  const [selectedAppModal, setSelectedAppModal] = useState(null);
  const [connectModalApp, setConnectModalApp] = useState(null);
  const [accountAlias, setAccountAlias] = useState('');
  const [connectionError, setConnectionError] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [isRequestModalOpen, setIsRequestModalOpen] = useState(false);
  const [requestedAppName, setRequestedAppName] = useState('');
  const [requestSubmitted, setRequestSubmitted] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);
  const [disconnectApp, setDisconnectApp] = useState(null);
  const connectUiRef = useRef(null);
  const pendingAuthorizationRef = useRef(null);

  useEffect(() => () => connectUiRef.current?.close(), []);

  const fetchIntegrations = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [connData, catData] = await Promise.all([
        api.request('GET', '/api/integrations'),
        api.request('GET', '/api/integrations/catalog')
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
            color: item.color || fallback.color || 'text-accent-fg bg-accent/10',
            actions: (item.actions && item.actions.length > 0) ? item.actions : (fallback.actions || []),
            description: item.description || fallback.description || '',
          };
        });
        setCatalog(merged);
      }
    } catch (err) {
      setLoadError('Could not load integrations. Please retry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
  }, []);

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

  const openConnectDialog = (app) => {
    setConnectionError(null);
    setConnectModalApp(app);
    setAccountAlias(`workspace-${app.name.toLowerCase().replace(/[^a-z0-9]/g, '')}`);
  };

  const handleExecuteConnect = async (appId) => {
    if (connecting) return;
    setConnecting(appId);
    setConnectionError(null);
    const alias = accountAlias.trim();
    const name = connectModalApp?.name || appId;
    const activate = async (connectionId) => {
      try {
        await api.request('POST', `/api/integrations/${appId}/activate`, {
          connection_id: connectionId,
          account_identifier: alias || undefined,
        });
      } catch (error) {
        // Permanent rejection needs fresh authorization. Network/server faults
        // keep the existing authorization available for a verification retry.
        if ([400, 401, 403, 404, 409, 422].includes(error?.status)) {
          pendingAuthorizationRef.current = null;
        }
        throw error;
      }
      pendingAuthorizationRef.current = null;
      triggerConfetti();
      setToastMessage(`Connected ${name}.`);
      setTimeout(() => setToastMessage(null), 4000);
      setConnectModalApp(null);
      await fetchIntegrations();
    };
    try {
      if (pendingAuthorizationRef.current?.appId === appId) {
        try {
          await activate(pendingAuthorizationRef.current.connectionId);
        } finally {
          setConnecting(null);
        }
        return;
      }
      const data = await api.request('POST', `/api/integrations/${appId}/connect`, {
        base_redirect_uri: `${window.location.origin}/api/integrations/callback`,
        account_identifier: alias || undefined,
      });
      if (data?.status !== 'INITIATED' || !data?.session_token) {
        throw new Error('Secure connection form unavailable. Please contact your administrator.');
      }
      let activating = false;
      let completed = false;
      const nango = new Nango({ connectSessionToken: data.session_token });
      connectUiRef.current?.close();
      connectUiRef.current = nango.openConnectUI({
        sessionToken: data.session_token,
        detectClosedAuthWindow: true,
        onEvent: async (event) => {
          if (event.type === 'connect' && !activating && !completed) {
            activating = true;
            try {
              const connectionId = event.payload?.connectionId;
              if (!connectionId) throw new Error('Authorization returned no connection. Please retry.');
              pendingAuthorizationRef.current = { appId, connectionId };
              await activate(connectionId);
              completed = true;
            } catch {
              setConnectionError('Connection could not be verified. Please retry or contact your administrator.');
            } finally {
              connectUiRef.current?.close();
              connectUiRef.current = null;
              activating = false;
              setConnecting(null);
            }
          } else if (event.type === 'error') {
            setConnectionError('Authorization did not complete. Please retry the secure connection.');
            connectUiRef.current?.close();
            connectUiRef.current = null;
            setConnecting(null);
          } else if (event.type === 'close' && !activating) {
            setConnecting(null);
          }
        },
      });
    } catch (error) {
      setConnectionError(connectFailureMessage(error));
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
      setToastMessage('Request sent. We will review it and get back to you.');
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

  // Connections whose credentials can no longer be refreshed. Agents cannot use
  // them, so the card asks for a reconnect instead of silently showing "Connect".
  const reauthAppKeys = useMemo(() => {
    const set = new Set();
    connections.forEach(c => {
      if (c.status === 'ERROR' && c.needs_reauth && c.app_name) set.add(normalizeAppKey(c.app_name));
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

  const timingLabel = (app) => (app?.timing === 'in_call' ? 'During calls' : 'After calls');
  const iconTileClass = (app) => {
    const brandColor = BRAND_COLORS[app?.id] || CATEGORY_COLORS[app?.category] || FALLBACK_COLOR;
    return `${brandColor.bg} ${brandColor.text}`;
  };
  const tabClass = (active) =>
    `shrink-0 inline-flex items-center gap-1.5 rounded-[8px] px-3 py-1.5 min-h-[36px] text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
      active ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
    }`;
  const tabCountClass = (active) =>
    `rounded-pill px-1.5 text-meta font-mono tabular-nums ${active ? 'bg-surface-subtle text-ink' : 'bg-surface text-fg-body'}`;
  const overlayClass = 'fixed inset-0 z-50 flex items-center justify-center bg-ink/60 backdrop-blur-sm p-4 animate-in fade-in duration-200';
  const dialogClass = 'bg-surface border border-line rounded-card w-full shadow-craft-lg animate-in zoom-in-95 duration-200';
  const closeButtonClass = 'shrink-0 -mr-2 -mt-1 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-control text-fg-muted hover:text-ink hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors';
  const inputClass = 'w-full px-3.5 py-2 min-h-[44px] sm:min-h-[38px] text-base sm:text-ui bg-surface border border-line rounded-control focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle';

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-20 font-sans">
      {/* Toast notification */}
      {toastMessage && (
        <div role="status" className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-6 sm:bottom-6 z-50 bg-ink text-white px-4 py-3 rounded-control shadow-craft-lg flex items-center gap-3 text-ui font-medium animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="w-6 h-6 rounded-full bg-success/25 text-success-line flex items-center justify-center flex-shrink-0">
            <CheckCheck className="w-3.5 h-3.5" aria-hidden="true" />
          </div>
          <span className="min-w-0">{toastMessage}</span>
        </div>
      )}

      <PageHeader
        title="Integrations"
        description="Connect the apps your agents use during and after calls, such as your calendar, CRM or helpdesk."
        actions={
          <>
            <TactileButton
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => setIsRequestModalOpen(true)}
              data-testid="request-app-btn"
            >
              Request custom integration
            </TactileButton>
            <TactileButton
              variant="ghost"
              size="icon"
              icon={RefreshCw}
              onClick={fetchIntegrations}
              disabled={loading}
              title="Refresh list"
              aria-label="Refresh list"
              className={loading ? '[&_svg]:animate-spin' : ''}
            />
          </>
        }
      >
        <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="integrations-summary">
          <Badge tone={connectedCount > 0 ? 'success' : 'neutral'} dot>
            {connectedCount} connected
          </Badge>
          {reauthAppKeys.size > 0 && (
            <Badge tone="danger" dot>
              {reauthAppKeys.size} need{reauthAppKeys.size === 1 ? 's' : ''} reconnecting
            </Badge>
          )}
          <span className="text-ui text-fg-muted">{catalog.length} apps available</span>
        </div>
      </PageHeader>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-warning-line bg-warning-soft px-4 py-3 text-copy text-warning-fg">
          <span className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            {loadError}
          </span>
          <TactileButton variant="secondary" size="sm" onClick={fetchIntegrations}>Retry</TactileButton>
        </div>
      )}

      {/* View tabs */}
      <div className="max-w-full overflow-x-auto no-scrollbar">
        <div role="tablist" aria-label="Integrations view" className="inline-flex items-center gap-0.5 rounded-control border border-line bg-surface-subtle p-0.5">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'all'}
            onClick={() => setActiveTab('all')}
            data-testid="tab-all-integrations"
            className={tabClass(activeTab === 'all')}
          >
            All integrations
            <span className={tabCountClass(activeTab === 'all')}>{catalog.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'connected'}
            onClick={() => setActiveTab('connected')}
            data-testid="tab-connected"
            className={tabClass(activeTab === 'connected')}
          >
            Connected
            <span className={tabCountClass(activeTab === 'connected')}>{connectedCount}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'guide'}
            onClick={() => setActiveTab('guide')}
            data-testid="tab-guide"
            className={tabClass(activeTab === 'guide')}
          >
            How connections work
          </button>
        </div>
      </div>

      {/* All and connected integrations */}
      {activeTab !== 'guide' && (
        <>
          {/* Search and category filter */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative flex min-w-0 flex-1 items-center sm:max-w-md">
              <span className="sr-only">Search integrations</span>
              <Search className="pointer-events-none absolute left-3 w-4 h-4 text-fg-subtle" aria-hidden="true" />
              <input
                type="text"
                data-testid="integration-search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={activeTab === 'connected' ? 'Search connected apps' : 'Search apps, like Calendly or Shopify'}
                className="w-full min-w-0 pl-9 pr-10 h-11 sm:h-9 text-base sm:text-ui bg-surface border border-line rounded-control focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 text-ink placeholder:text-fg-subtle"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                  className="absolute right-1 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-control text-fg-muted hover:text-ink hover:bg-canvas"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </label>

            <div className="flex min-w-0 items-center gap-2">
              <label className="flex min-w-0 flex-1 items-center gap-2 text-ui text-fg-body sm:flex-initial">
                <span className="sr-only">Category</span>
                <select
                  data-testid="integration-filter-select"
                  value={filterMode}
                  onChange={(e) => setFilterMode(e.target.value)}
                  className="h-11 sm:h-9 w-full min-w-0 rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 cursor-pointer"
                >
                  <option value="all">All categories</option>
                  <option value="scheduling">Calendar and scheduling</option>
                  <option value="crm">CRM and sales</option>
                  <option value="support">Customer support</option>
                  <option value="ecommerce">E-commerce and payments</option>
                  <option value="communication">Team messaging</option>
                  <option value="email">Email</option>
                  <option value="database">Databases and spreadsheets</option>
                  <option value="productivity">Tasks and projects</option>
                </select>
              </label>
              <span className="shrink-0 text-ui text-fg-muted whitespace-nowrap">
                <span className="font-mono tabular-nums">{filteredCatalog.length}</span> {filteredCatalog.length === 1 ? 'app' : 'apps'}
              </span>
            </div>
          </div>

          {/* Grid of integrations */}
          {filteredCatalog.length === 0 ? (
            activeTab === 'connected' && !searchQuery ? (
              <SolidCard padding="p-0"><EmptyState
                icon={Layers}
                title="No apps connected yet"
                description="Connect your calendar, CRM or messaging app so your agents can book, look up and update things during calls."
                action={
                  <TactileButton variant="primary" size="sm" onClick={() => setActiveTab('all')}>
                    Browse all {catalog.length} integrations
                  </TactileButton>
                }
              /></SolidCard>
            ) : (
              <SolidCard padding="p-0"><EmptyState
                icon={Search}
                title="No apps match"
                description={searchQuery ? `Nothing matches "${searchQuery}". Try a different word.` : 'Nothing matches this category.'}
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <TactileButton variant="secondary" size="sm" onClick={() => { setSearchQuery(''); setFilterMode('all'); }}>
                      Clear filters
                    </TactileButton>
                    <TactileButton variant="primary" size="sm" onClick={() => setIsRequestModalOpen(true)}>
                      Request integration
                    </TactileButton>
                  </div>
                }
              /></SolidCard>
            )
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filteredCatalog.map(app => {
                const isConnected = connectedAppKeys.has(normalizeAppKey(app.id));
                const needsReauth = !isConnected && reauthAppKeys.has(normalizeAppKey(app.id));
                const isConnectingThis = connecting === app.id;

                return (
                  <SolidCard
                    key={app.id}
                    padding="p-4"
                    className={`flex min-w-0 flex-col justify-between transition-[border-color,box-shadow] hover:shadow-craft-sm ${
                      isConnected ? '!border-success-line' : needsReauth ? '!border-danger-line' : 'hover:!border-line-strong'
                    }`}
                  >
                    <div className="min-w-0">
                      {/* Icon, name, category */}
                      <div className="flex items-start gap-3">
                        <div className={`w-10 h-10 rounded-control flex items-center justify-center flex-shrink-0 ${iconTileClass(app)}`} aria-hidden="true">
                          {getIcon(app.iconName, 'w-5 h-5')}
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3 className="text-copy font-semibold text-ink break-words" title={app.name}>
                            {app.name}
                          </h3>
                          <p className="text-meta text-fg-muted">
                            {app.category}{app.category ? ' · ' : ''}{timingLabel(app)}
                          </p>
                        </div>
                      </div>

                      {/* Status and sign-in method */}
                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        {isConnected ? (
                          <Badge tone="success" dot>Connected</Badge>
                        ) : needsReauth ? (
                          <Badge
                            tone="danger"
                            dot
                            data-testid={`reauth-badge-${app.id.toLowerCase()}`}
                            title="The connected account's sign-in expired or was revoked. Agents cannot use it until you reconnect."
                          >
                            Reconnect needed
                          </Badge>
                        ) : (
                          <Badge tone="neutral">Not connected</Badge>
                        )}
                        <Badge
                          tone="neutral"
                          title={app.auth_type === 'oauth' ? 'Connect by signing in to the app. No API key needed.' : 'Connect with an API key or token from the app.'}
                        >
                          {app.auth_type === 'oauth' ? 'Sign in' : 'API key'}
                        </Badge>
                      </div>

                      {/* Description */}
                      <p className="mt-3 text-ui text-fg-body line-clamp-2">
                        {app.description}
                      </p>

                      {/* First actions */}
                      {app.actions && app.actions.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {app.actions.slice(0, 2).map((act, i) => (
                            <span key={i} title={act} className="text-meta bg-canvas border border-line px-2 py-0.5 rounded-pill text-fg-body truncate max-w-full">
                              {act}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Footer: actions list and connect / disconnect */}
                    <div className="mt-4 pt-3 border-t border-line flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedAppModal(app)}
                        className="min-h-[36px] -ml-1 px-1 rounded-control text-ui text-fg-body hover:text-accent-fg font-medium flex items-center gap-1 group/btn transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        <span>{app.actions?.length || 2} actions</span>
                        <ArrowRight className="w-3.5 h-3.5 group-hover/btn:translate-x-0.5 transition-transform" aria-hidden="true" />
                      </button>

                      <div className="shrink-0">
                        {isConnected ? (
                          <TactileButton
                            variant="ghost"
                            size="sm"
                            onClick={() => promptDisconnect(app)}
                            data-testid={`disconnect-btn-${app.id.toLowerCase()}`}
                            title="Disconnect integration"
                          >
                            Disconnect
                          </TactileButton>
                        ) : app.oauth_ready === false ? (
                          <span
                            data-testid={`not-ready-${app.id.toLowerCase()}`}
                            className="inline-flex px-2.5 py-1 text-meta font-medium text-fg-body bg-surface-subtle rounded-pill"
                            title="Your administrator has not enabled this integration yet."
                          >
                            Not available yet
                          </span>
                        ) : (
                          <TactileButton
                            variant={needsReauth ? 'danger' : 'primary'}
                            size="sm"
                            onClick={() => openConnectDialog(app)}
                            disabled={isConnectingThis}
                            loading={isConnectingThis}
                            data-testid={`connect-btn-${app.id.toLowerCase()}`}
                          >
                            {isConnectingThis ? 'Connecting…' : needsReauth ? 'Reconnect' : 'Connect'}
                          </TactileButton>
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

      {/* How connections work */}
      {activeTab === 'guide' && (
        <Section
          title="How connections work"
          description="What happens when you connect an app, and how your agents use it."
        >
          <ol className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <li className="p-4 rounded-control bg-canvas border border-line space-y-2">
              <div className="w-7 h-7 rounded-full bg-surface border border-line text-ui font-semibold text-ink flex items-center justify-center" aria-hidden="true">1</div>
              <h3 className="text-copy font-semibold text-ink">You sign in to the app</h3>
              <p className="text-ui text-fg-body">
                Select <strong className="font-semibold text-ink">Connect</strong> and sign in on the app's own page, such as Google, HubSpot or Slack, then approve the access it asks for.
              </p>
              <p className="text-meta text-fg-muted flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                Dialtact never sees your password.
              </p>
            </li>
            <li className="p-4 rounded-control bg-canvas border border-line space-y-2">
              <div className="w-7 h-7 rounded-full bg-surface border border-line text-ui font-semibold text-ink flex items-center justify-center" aria-hidden="true">2</div>
              <h3 className="text-copy font-semibold text-ink">Access stays with your workspace</h3>
              <p className="text-ui text-fg-body">
                The access the app gives us is stored encrypted and only your workspace's agents can use it. You can disconnect at any time.
              </p>
              <p className="text-meta text-fg-muted flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                Stored encrypted, kept separate from other workspaces.
              </p>
            </li>
            <li className="p-4 rounded-control bg-canvas border border-line space-y-2">
              <div className="w-7 h-7 rounded-full bg-surface border border-line text-ui font-semibold text-ink flex items-center justify-center" aria-hidden="true">3</div>
              <h3 className="text-copy font-semibold text-ink">Your agents use it on calls</h3>
              <p className="text-ui text-fg-body">
                When a caller asks to book a time, the agent checks your connected calendar and confirms only after the app says the booking went through. How quickly depends on the app.
              </p>
              <p className="text-meta text-fg-muted flex items-center gap-1.5">
                <Check className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                Confirmed by the app before the caller hears it.
              </p>
            </li>
          </ol>

          <div className="mt-4 flex items-start gap-2 rounded-control border border-info-line bg-info-soft p-3 text-ui text-info-fg">
            <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
            <p>
              A connection is switched on only after the sign-in is confirmed for your workspace. If you cancel the sign-in, the app stays disconnected.
            </p>
          </div>
        </Section>
      )}

      {/* Connect dialog */}
      {connectModalApp && (
        <div className={overlayClass}>
          <div role="dialog" aria-modal="true" aria-labelledby="integration-connect-title" className={`${dialogClass} p-5 sm:p-6 max-w-lg max-h-[90vh] overflow-y-auto space-y-5`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className={`w-11 h-11 rounded-control flex items-center justify-center shrink-0 ${iconTileClass(connectModalApp)}`} aria-hidden="true">
                  {getIcon(connectModalApp.iconName, 'w-6 h-6')}
                </div>
                <div className="min-w-0">
                  <h3 id="integration-connect-title" className="text-title text-ink break-words">Connect {connectModalApp.name}</h3>
                  <p className="text-ui text-fg-muted">
                    {connectModalApp.category}{connectModalApp.category ? ' · ' : ''}{timingLabel(connectModalApp)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConnectModalApp(null)}
                className={closeButtonClass}
                aria-label="Close connect dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              {connectModalApp.auth_type === 'oauth' ? (
                <div className="p-4 rounded-control bg-canvas border border-line space-y-1.5">
                  <div className="flex items-center gap-2 text-ui font-semibold text-ink">
                    <ShieldCheck className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
                    <span>Sign in with {connectModalApp.name}</span>
                  </div>
                  <p className="text-ui text-fg-body">
                    Continue opens <strong className="font-semibold text-ink">{connectModalApp.name}</strong>'s own sign-in page. Approve access with your existing account; no API key needed.
                  </p>
                </div>
              ) : (
                <div className="p-4 rounded-control bg-canvas border border-line space-y-1.5">
                  <div className="flex items-center gap-2 text-ui font-semibold text-ink">
                    <Key className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
                    <span>Connect with an API key</span>
                  </div>
                  <p className="text-ui text-fg-body">
                    <strong className="font-semibold text-ink">{connectModalApp.name}</strong> connects with a key from your account. Continue to a secure form that asks for the details this app needs.
                  </p>
                </div>
              )}

              <div className="space-y-1.5">
                <label htmlFor="integration-account-alias" className="block text-ui font-medium text-ink">
                  Account label
                </label>
                <input
                  type="text"
                  id="integration-account-alias"
                  maxLength={255}
                  value={accountAlias}
                  onChange={(e) => setAccountAlias(e.target.value)}
                  placeholder="For example sales-team@company.com or Main CRM"
                  className={inputClass}
                />
                <p className="text-meta text-fg-muted">A name to tell this account apart if you connect more than one.</p>
              </div>

              <div className="space-y-1.5">
                <h4 className="text-ui font-medium text-ink">What your agents can do</h4>
                <ul className="space-y-1">
                  {(connectModalApp.actions || ['Check Status', 'Execute Action']).map((action, i) => (
                    <li key={i} className="flex items-start gap-2 text-ui text-fg-body">
                      <Check className="w-3.5 h-3.5 text-success-fg flex-shrink-0 mt-0.5" aria-hidden="true" />
                      <span className="min-w-0 break-words">{action}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {connectionError && (
              <p role="alert" data-testid="connection-error" className="text-ui text-danger-fg bg-danger-soft border border-danger-line rounded-control p-3">{connectionError}</p>
            )}

            <div className="pt-4 border-t border-line flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <span className="text-meta text-fg-muted flex items-center gap-1.5 justify-center sm:justify-start">
                <Lock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                <span>Stored encrypted. Disconnect at any time.</span>
              </span>

              <div className="flex items-center gap-2">
                <TactileButton
                  variant="ghost"
                  size="md"
                  onClick={() => setConnectModalApp(null)}
                  className="flex-1 sm:flex-initial justify-center"
                >
                  Cancel
                </TactileButton>
                <TactileButton
                  variant="brand"
                  size="md"
                  data-testid="confirm-connect-btn"
                  onClick={() => handleExecuteConnect(connectModalApp.id)}
                  disabled={connecting === connectModalApp.id}
                  loading={connecting === connectModalApp.id}
                  className="flex-1 sm:flex-initial justify-center"
                >
                  {connecting === connectModalApp.id ? 'Opening…' : (
                    <>
                      Continue
                      <ArrowUpRight className="w-4 h-4" aria-hidden="true" />
                    </>
                  )}
                </TactileButton>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Actions preview dialog */}
      {selectedAppModal && (
        <div className={overlayClass}>
          <div role="dialog" aria-modal="true" aria-labelledby="integration-actions-title" className={`${dialogClass} p-5 sm:p-6 max-w-md max-h-[90vh] overflow-y-auto space-y-4`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className={`w-10 h-10 rounded-control flex items-center justify-center shrink-0 ${iconTileClass(selectedAppModal)}`} aria-hidden="true">
                  {getIcon(selectedAppModal.iconName, 'w-5 h-5')}
                </div>
                <div className="min-w-0">
                  <h3 id="integration-actions-title" className="text-title text-ink break-words">{selectedAppModal.name}</h3>
                  <p className="text-ui text-fg-muted">
                    {selectedAppModal.auth_type === 'api_key' ? 'API key' : 'Sign in'} · {timingLabel(selectedAppModal)}
                  </p>
                </div>
              </div>
              <button
                type="button"
                data-testid="action-modal-close-btn"
                onClick={() => setSelectedAppModal(null)}
                aria-label="Close"
                className={closeButtonClass}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-ui text-fg-body">
              {selectedAppModal.description}
            </p>

            <div className="space-y-2">
              <h4 className="text-ui font-medium text-ink">
                What your agents can do
              </h4>
              <ul className="space-y-1.5">
                {(selectedAppModal.actions || ['Check Status', 'Execute Action']).map((action, idx) => (
                  <li key={idx} className="flex items-center justify-between gap-3 p-2.5 rounded-control bg-canvas border border-line text-ui">
                    <span className="min-w-0 break-words font-medium text-ink">{action}</span>
                    <Badge tone={selectedAppModal.timing === 'in_call' ? 'info' : 'neutral'}>
                      {timingLabel(selectedAppModal)}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>

            <div className="pt-3 border-t border-line flex justify-end">
              <TactileButton variant="secondary" size="sm" onClick={() => setSelectedAppModal(null)}>
                Close
              </TactileButton>
            </div>
          </div>
        </div>
      )}

      {/* Request app dialog */}
      {isRequestModalOpen && (
        <div className={overlayClass}>
          <div role="dialog" aria-modal="true" aria-labelledby="integration-request-title" className={`${dialogClass} p-5 sm:p-6 max-w-md space-y-4`}>
            <div className="flex items-start justify-between gap-3">
              <h3 id="integration-request-title" className="text-title text-ink">
                Request custom integration
              </h3>
              <button
                type="button"
                onClick={() => setIsRequestModalOpen(false)}
                aria-label="Close"
                className={closeButtonClass}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-ui text-fg-body">
              Need an app that is not listed, like a private ERP or an internal database? Tell us which one and we will look into it.
            </p>

            <form onSubmit={handleRequestSubmit} className="space-y-4">
              <div>
                <label htmlFor="integration-request-name" className="block text-ui font-medium text-ink mb-1.5">
                  App or tool name
                </label>
                <input
                  id="integration-request-name"
                  type="text"
                  required
                  value={requestedAppName}
                  onChange={(e) => setRequestedAppName(e.target.value)}
                  placeholder="e.g. NetSuite, Workday, Custom CRM..."
                  className={inputClass}
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-line">
                <TactileButton type="button" variant="ghost" size="sm" onClick={() => setIsRequestModalOpen(false)}>
                  Cancel
                </TactileButton>
                <TactileButton type="submit" variant="brand" size="sm" disabled={requestSubmitted} icon={requestSubmitted ? Check : undefined}>
                  {requestSubmitted ? 'Submitted' : 'Submit request'}
                </TactileButton>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Disconnect confirmation */}
      {disconnectApp && (
        <div className={overlayClass}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="integration-disconnect-title" className={`${dialogClass} p-5 sm:p-6 max-w-sm space-y-4`}>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-control bg-danger-soft flex items-center justify-center flex-shrink-0" aria-hidden="true">
                <Trash2 className="w-5 h-5 text-danger-fg" />
              </div>
              <div className="min-w-0">
                <h3 id="integration-disconnect-title" className="text-title text-ink break-words">Disconnect {disconnectApp.name || disconnectApp.id}?</h3>
                <p className="text-ui text-fg-muted">Your agents will lose access</p>
              </div>
            </div>
            <p className="text-ui text-fg-body">
              Your agents will no longer be able to use this app during or after calls. You can connect it again later.
            </p>
            <div className="flex justify-end gap-2 pt-3 border-t border-line">
              <TactileButton type="button" variant="ghost" size="sm" onClick={() => setDisconnectApp(null)}>
                Cancel
              </TactileButton>
              <TactileButton
                type="button"
                variant="danger"
                size="sm"
                data-testid="confirm-disconnect-btn"
                onClick={confirmDisconnect}
              >
                Disconnect
              </TactileButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
