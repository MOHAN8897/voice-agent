import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Volume2,
  VolumeX,
  Play,
  Square,
  Check,
  CheckCircle2,
  Radio,
  Sliders,
  Sparkles,
  Info,
  RotateCcw,
  Languages,
  Mic,
  Activity,
  Layers,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';
import { voiceAgent } from '../../../services/voiceAgent';
import { api } from '../../../services/api';
import { showToast } from '../../ui/ToastHost';

/**
 * Curated Conversational and Commercial / Promotional voice profiles from Gemini TTS and Sarvam TTS.
 */
export const VOICE_CATALOG = [
  // Conversational Voices
  {
    id: 'zephyr',
    name: 'Zephyr',
    gender: 'female',
    tone: 'Bright & clear',
    category: 'conversational',
    useCase: 'Conversational Assistant & Inquiries',
    sampleText: 'Hello, this is Zephyr. I can assist you with bookings, orders, and inquiries. How can I help you today?',
    sampleUrl: '/audio/voxly/samples/zephyr.wav',
    duration: '8.5s',
  },
  {
    id: 'puck',
    name: 'Puck',
    gender: 'male',
    tone: 'Upbeat & conversational',
    category: 'conversational',
    useCase: 'Conversational Outreach & Bookings',
    sampleText: 'Hello! I am Puck. I can help explore our latest inventory, book appointments, or answer questions. What can I get started for you?',
    sampleUrl: '/audio/voxly/samples/puck.wav',
    duration: '8.6s',
  },
  {
    id: 'aoede',
    name: 'Aoede',
    gender: 'female',
    tone: 'Breezy & engaging',
    category: 'conversational',
    useCase: 'Conversational Host & Dialogues',
    sampleText: 'Welcome! I am Aoede, your virtual assistant. How can I assist you today?',
    sampleUrl: '/audio/voxly/samples/aoede.wav',
    duration: '8.3s',
  },
  {
    id: 'leda',
    name: 'Leda',
    gender: 'female',
    tone: 'Youthful & pleasant',
    category: 'conversational',
    useCase: 'Conversational Care & Hospitality',
    sampleText: 'Thank you for calling. I am here to assist with your bookings, questions, and customer care. How may I help you?',
    sampleUrl: '/audio/voxly/samples/leda.wav',
    duration: '8.2s',
  },
  {
    id: 'shubh',
    name: 'Shubh',
    gender: 'male',
    tone: 'Conversational & crisp',
    category: 'conversational',
    useCase: 'Conversational Support & Queries',
    sampleText: 'నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?',
    sampleUrl: '/audio/voxly/samples/shubh.wav',
    duration: '6.5s',
  },
  {
    id: 'priya',
    name: 'Priya',
    gender: 'female',
    tone: 'Warm & conversational',
    category: 'conversational',
    useCase: 'Conversational Care & Appointments',
    sampleText: 'నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?',
    sampleUrl: '/audio/voxly/samples/priya.wav',
    duration: '6.8s',
  },
  {
    id: 'pooja',
    name: 'Pooja',
    gender: 'female',
    tone: 'Gentle & conversational',
    category: 'conversational',
    useCase: 'Conversational Intake & Triage',
    sampleText: 'నమస్కారం, మీ వివరాలను సరిచూసేందుకు సహాయపడతాను.',
    sampleUrl: '/audio/voxly/samples/pooja.wav',
    duration: '6.2s',
  },
  {
    id: 'simran',
    name: 'Simran',
    gender: 'female',
    tone: 'Cheerful & welcoming',
    category: 'conversational',
    useCase: 'Conversational Reception & Services',
    sampleText: 'నమస్కారం, స్వాగతం! మీకు ఎలా సహాయపడగలను?',
    sampleUrl: '/audio/voxly/samples/simran.wav',
    duration: '6.4s',
  },

  // Commercial / Promotional Voices
  {
    id: 'kore',
    name: 'Kore',
    gender: 'female',
    tone: 'Firm & authoritative',
    category: 'promotional',
    useCase: 'Commercial Promotions & Direct Announcements',
    sampleText: 'Thank you for calling. I can help you schedule appointments, verify records, and answer questions. What can I do for you today?',
    sampleUrl: '/audio/voxly/samples/kore.wav',
    duration: '8.4s',
  },
  {
    id: 'charon',
    name: 'Charon',
    gender: 'male',
    tone: 'Informative & calm',
    category: 'promotional',
    useCase: 'Commercial Broadcasts & Operations',
    sampleText: 'You have reached Dispatch Services. I can schedule emergency maintenance, technician visits, or system inspections. What can I do for you?',
    sampleUrl: '/audio/voxly/samples/charon.wav',
    duration: '8.9s',
  },
  {
    id: 'fenrir',
    name: 'Fenrir',
    gender: 'male',
    tone: 'Confident & excitable',
    category: 'promotional',
    useCase: 'Commercial Outreach & Sales Inquiries',
    sampleText: 'Thanks for calling! We have exclusive viewings and consultations available this week. What area interests you?',
    sampleUrl: '/audio/voxly/samples/fenrir.wav',
    duration: '8.8s',
  },
  {
    id: 'sulafat',
    name: 'Sulafat',
    gender: 'female',
    tone: 'Warm & persuasive',
    category: 'promotional',
    useCase: 'Commercial Outreach & Customer Promotions',
    sampleText: 'Thank you for calling. I can guide you through our special packages and promotions.',
    sampleUrl: '/audio/voxly/samples/sulafat.wav',
    duration: '7.8s',
  },
  {
    id: 'pulcherrima',
    name: 'Pulcherrima',
    gender: 'female',
    tone: 'Forward & dynamic',
    category: 'promotional',
    useCase: 'Commercial Announcements & Brand Outreach',
    sampleText: 'Hello! I am your brand assistant, ready to assist with latest offers and updates.',
    sampleUrl: '/audio/voxly/samples/pulcherrima.wav',
    duration: '8.0s',
  },
  {
    id: 'neha',
    name: 'Neha',
    gender: 'female',
    tone: 'Friendly & persuasive',
    category: 'promotional',
    useCase: 'Commercial / Promotional & Sales Outreach',
    sampleText: 'నమస్కారం, మా ఆఫర్ల గురించి మీకు వివరించడానికి సిద్ధంగా ఉన్నాను.',
    sampleUrl: '/audio/voxly/samples/neha.wav',
    duration: '6.7s',
  },
  {
    id: 'rahul',
    name: 'Rahul',
    gender: 'male',
    tone: 'Energetic & dynamic',
    category: 'promotional',
    useCase: 'Commercial / Promotional & Direct Booking',
    sampleText: 'నమస్కారం, మీ అపాయింట్‌మెంట్ బుకింగ్ కోసం నేను సహాయం చేయగలను.',
    sampleUrl: '/audio/voxly/samples/rahul.wav',
    duration: '6.9s',
  },

  // Expressive Indic Personas
  {
    id: 'nalini',
    name: 'Nalini',
    gender: 'female',
    tone: 'Warm & expressive',
    category: 'conversational',
    useCase: 'Conversational Customer Support',
    sampleText: 'నమస్కారం, నేను నళిని. మీకు ఎలా సహాయపడగలను?',
    sampleUrl: '/audio/voxly/samples/voice-gnani-1.wav',
    duration: '7.1s',
  },
  {
    id: 'shivani',
    name: 'Shivani',
    gender: 'female',
    tone: 'Clear & friendly',
    category: 'conversational',
    useCase: 'Frontdesk & Concierge Services',
    sampleText: 'నమస్కారం! నేను శివాని. మీకు ఎలాంటి సహాయం కావాలి?',
    sampleUrl: '/audio/voxly/samples/voice-gnani-2.wav',
    duration: '6.9s',
  },
  {
    id: 'lakshmi',
    name: 'Lakshmi',
    gender: 'female',
    tone: 'Soft & engaging',
    category: 'conversational',
    useCase: 'Healthcare & Patient Intake',
    sampleText: 'నమస్కారం, మీ ఆరోగ్య మరియు సంరక్షణ వివరాలను సరిచూసేందుకు సహాయపడతాను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-1.wav',
    duration: '7.4s',
  },
  {
    id: 'chitra',
    name: 'Chitra',
    gender: 'female',
    tone: 'Professional & steady',
    category: 'promotional',
    useCase: 'Commercial Advisory & Outreach',
    sampleText: 'నమస్కారం! మా ప్రత్యేక ఆఫర్లు మరియు సేవలను పరిశీలించడానికి నేను సిద్ధంగా ఉన్నాను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-2.wav',
    duration: '7.2s',
  },
  {
    id: 'pranav',
    name: 'Pranav',
    gender: 'male',
    tone: 'Crisp & natural',
    category: 'conversational',
    useCase: 'Technical Support & Inquiries',
    sampleText: 'నమస్కారం, నేను ప్రణవ్. మీ సాంకేతిక ప్రశ్నలకు సమాధానాలు ఇవ్వగలను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-2.wav',
    duration: '6.8s',
  },
  {
    id: 'avinash',
    name: 'Avinash',
    gender: 'male',
    tone: 'Authoritative & calm',
    category: 'promotional',
    useCase: 'Commercial Property & Consultations',
    sampleText: 'నమస్కారం, రియల్ ఎస్టేట్ మరియు ప్రాజెక్ట్ వివరాలను మీకు తెలియజేయడానికి నేను ఇక్కడ ఉన్నాను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-1.wav',
    duration: '7.5s',
  },
  {
    id: 'prakash',
    name: 'Prakash',
    gender: 'male',
    tone: 'Direct & warm',
    category: 'conversational',
    useCase: 'Logistics & Operational Updates',
    sampleText: 'నమస్కారం, మీ డెలివరీ మరియు సేవల తాజా సమాచారం కోసం నేను సహాయపడతాను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-2.wav',
    duration: '6.6s',
  },
  {
    id: 'sanjay',
    name: 'Sanjay',
    gender: 'male',
    tone: 'Dynamic & persuasive',
    category: 'promotional',
    useCase: 'Sales Campaigns & Fast Booking',
    sampleText: 'నమస్కారం, ఈ వారం ప్రత్యేక బుకింగ్‌ల గురించి మీకు తెలియజేయడానికి కాల్ చేస్తున్నాను.',
    sampleUrl: '/audio/voxly/samples/voice-gnani-1.wav',
    duration: '7.0s',
  },

  // Ultra-Fast Conversational Personas (Cartesia Engine)
  {
    id: 'priya',
    name: 'Priya',
    gender: 'female',
    tone: 'Warm, natural & conversational',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'hi-IN',
    useCase: 'Hindi & Telugu Regional Support',
    sampleText: 'नमस्ते! मैं प्रिया हूँ, आपकी सहायता के लिए सदैव उपलब्ध हूँ।',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.5s',
  },
  {
    id: 'kiara',
    name: 'Kiara',
    gender: 'female',
    tone: 'Upbeat, pleasant & clear',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'en-IN',
    useCase: 'Hospitality & Onboarding Concierge',
    sampleText: 'Hello! I am Kiara, happy to guide you through our services.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.3s',
  },
  {
    id: 'indian-lady',
    name: 'Indian Lady',
    gender: 'female',
    tone: 'Polite, composed & supportive',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'en-IN',
    useCase: 'Priority Helpdesk & Customer Care',
    sampleText: 'Good day. How may I be of service to you today?',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.4s',
  },
  {
    id: 'bhavani',
    name: 'Bhavani',
    gender: 'female',
    tone: 'Warm, natural & conversational',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'te-IN',
    useCase: 'Telugu Regional Support & Outreach',
    sampleText: 'నమస్కారం! నేను భవానిని. మీ ప్రశ్నలకు సమాధానం ఇవ్వడానికి నేను సిద్ధంగా ఉన్నాను.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.4s',
  },
  {
    id: 'charan',
    name: 'Charan',
    gender: 'male',
    tone: 'Crisp, conversational & friendly',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'te-IN',
    useCase: 'Telugu Consultations & Bookings',
    sampleText: 'నమస్కారం! చరణ్ ఇక్కడ, మీ సర్వీస్ అభ్యర్థనలను ధృవీకరించడానికి నేను సహాయం చేస్తాను.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.6s',
  },
  {
    id: 'aarti',
    name: 'Aarti',
    gender: 'female',
    tone: 'Friendly, clear & engaging',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'hi-IN',
    useCase: 'Hindi Customer Care & Inquiry',
    sampleText: 'नमस्ते! मैं आरती हूँ। आपकी पूछताछ और सहायता के लिए हमेशा उपलब्ध हूँ।',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.5s',
  },
  {
    id: 'amrit',
    name: 'Amrit',
    gender: 'male',
    tone: 'Professional, articulate & calm',
    category: 'promotional',
    accent: 'Indian',
    tag: 'Indian',
    language: 'hi-IN',
    useCase: 'Hindi Corporate & Advisory Services',
    sampleText: 'नमस्ते! मैं अमृत बोल रहा हूँ। आपके खाते और सेवाओं की जानकारी मैं साझा करूँगा।',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.8s',
  },
  {
    id: 'maya',
    name: 'Maya',
    gender: 'female',
    tone: 'Clear, modern & empathetic',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'en-IN',
    useCase: 'Indian English Concierge & Support',
    sampleText: 'Hello! I am Maya. I can quickly answer your questions and confirm your appointments.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.2s',
  },
  {
    id: 'devansh',
    name: 'Devansh',
    gender: 'male',
    tone: 'Crisp, confident & courteous',
    category: 'promotional',
    accent: 'Indian',
    tag: 'Indian',
    language: 'en-IN',
    useCase: 'Indian English Priority Dispatch & Sales',
    sampleText: 'Hi there, Devansh here. I am pleased to assist you with your schedule and inquiries today.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.5s',
  },
  {
    id: 'krishna',
    name: 'Krishna',
    gender: 'male',
    tone: 'Deep, confident & reassuring',
    category: 'conversational',
    accent: 'Indian',
    tag: 'Indian',
    language: 'te-IN',
    useCase: 'Telugu & Hindi Financial Consultations',
    sampleText: 'నమస్కారం! నేను కృష్ణ. మీ ఆర్థిక ప్రణాళికలో సహాయపడటానికి సిద్ధంగా ఉన్నాను.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.7s',
  },
  {
    id: 'aarav',
    name: 'Aarav',
    gender: 'male',
    tone: 'Crisp, dynamic & energetic',
    category: 'promotional',
    accent: 'Indian',
    tag: 'Indian',
    language: 'en-IN',
    useCase: 'Indian English Sales & Announcements',
    sampleText: 'Hi there! I am Aarav, reaching out to share our newest offers.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.4s',
  },
  {
    id: 'sarah',
    name: 'Sarah',
    gender: 'female',
    tone: 'Ultra-fast & natural',
    category: 'conversational',
    useCase: 'High-Speed Multilingual Inquiries',
    sampleText: 'Hello! I am Sarah. I can rapidly answer questions, check availability, and confirm reservations.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.5s',
  },
  {
    id: 'caleb',
    name: 'Caleb',
    gender: 'male',
    tone: 'Upbeat & friendly',
    category: 'conversational',
    useCase: 'Interactive Real-time Dialogue',
    sampleText: 'Hi there! Caleb here, ready to assist with your account, scheduled visits, or general questions.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.7s',
  },
  {
    id: 'jacqueline',
    name: 'Jacqueline',
    gender: 'female',
    tone: 'Warm & empathetic',
    category: 'conversational',
    useCase: 'Customer Care & Priority Helpdesk',
    sampleText: 'Thank you for reaching out. I am Jacqueline, and I am here to make sure your questions are resolved.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '7.0s',
  },
  {
    id: 'michael',
    name: 'Michael',
    gender: 'male',
    tone: 'Professional & clear',
    category: 'promotional',
    useCase: 'Corporate Briefings & Consultations',
    sampleText: 'Good day. I am Michael. Let us review the optimal plans and solutions tailored for your business.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '7.3s',
  },
  {
    id: 'skylar',
    name: 'Skylar',
    gender: 'female',
    tone: 'Empathetic & natural',
    category: 'conversational',
    useCase: 'Care Navigation & Advisory',
    sampleText: 'Hello! I am Skylar, guiding you step-by-step through appointments and check-in procedures.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.8s',
  },
  {
    id: 'daniel',
    name: 'Daniel',
    gender: 'male',
    tone: 'Authoritative & steady',
    category: 'promotional',
    useCase: 'Priority Dispatch & Notifications',
    sampleText: 'Attention: this is dispatch confirmation with Daniel. I will verify your service slot right away.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '6.9s',
  },
  {
    id: 'katie',
    name: 'Katie',
    gender: 'female',
    tone: 'Bright & energetic',
    category: 'promotional',
    useCase: 'Retail Highlights & Promotional Offers',
    sampleText: 'Hi! Katie here to share our exclusive new offers and limited-time opportunities.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-1.wav',
    duration: '6.4s',
  },
  {
    id: 'leo',
    name: 'Leo',
    gender: 'male',
    tone: 'Calm & engaging',
    category: 'conversational',
    useCase: 'Educational Briefs & Guided Walkthroughs',
    sampleText: 'Welcome. I am Leo, your virtual concierge, pleased to assist you with every detail today.',
    sampleUrl: '/audio/voxly/samples/voice-cartesia-2.wav',
    duration: '7.2s',
  },
];

const STACK_TIER_LABELS = {
  low: 'Economical Tier',
  medium: 'Standard Regional Tier',
  premium: 'Flagship Live Tier',
};
const BLOCKED_TENANT_TERMS = /\b(vobiz|telnyx|nango|exotel|plivo|composio|sarvam|gemini|openai|elevenlabs|deepgram|playht|murf|azure)\b/i;

function publicChoice(value) {
  return typeof value === 'string' && value.trim() && !BLOCKED_TENANT_TERMS.test(value);
}

function hasApprovedRetailRate(rate) {
  if (rate?.complete === true) {
    return [rate.usdMicrosPerMin, rate.inrPaisePerMin, rate.version].every(
      (value) => Number.isSafeInteger(value) && value > 0
    );
  }
  return Boolean(
    rate &&
      Number.isFinite(Number(rate.amount)) &&
      Number(rate.amount) >= 0 &&
      typeof rate.currency === 'string' &&
      /^[A-Z]{3}$/.test(rate.currency)
  );
}

function formatRetailRate(rate) {
  if (!hasApprovedRetailRate(rate)) return null;
  if (rate.complete === true) {
    return `${new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(rate.usdMicrosPerMin / 1_000_000)} / ${new Intl.NumberFormat(undefined, { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(rate.inrPaisePerMin / 100)} per min`;
  }
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: rate.currency,
      maximumFractionDigits: 2,
    }).format(Number(rate.amount));
  } catch {
    return `${rate.currency} ${Number(rate.amount).toFixed(2)}`;
  }
}

function publicEngines(profile, language) {
  if (!Array.isArray(profile?.engines)) return [];
  return profile.engines
    .filter((engine) => publicChoice(engine?.id) && publicChoice(engine?.label))
    .map((engine) => ({
      ...engine,
      models: (Array.isArray(engine.models) ? engine.models : [])
        .filter((model) => publicChoice(model?.id) && publicChoice(model?.label))
        .map((model) => ({
          ...model,
          voices: (Array.isArray(model.voices) ? model.voices : []).filter(
            (voice) =>
              publicChoice(voice?.id) &&
              publicChoice(voice?.label) &&
              Array.isArray(voice.languages) &&
              voice.languages.includes(language)
          ),
        }))
        .filter((model) => model.voices.length > 0),
    }))
    .filter((engine) => engine.models.length > 0);
}

function isSelectableProfile(profile, language) {
  if (
    !profile ||
    profile.ready !== true ||
    typeof profile.tier !== 'string' ||
    !profile.tier.trim() ||
    !Number.isSafeInteger(profile.profileRevision) ||
    profile.profileRevision < 0 ||
    !hasApprovedRetailRate(profile.retailRate)
  ) {
    return false;
  }
  return publicEngines(profile, language).length > 0;
}

function selectionFromAgent(agent) {
  const settings = agent?.voiceSettings;
  if (settings?.stackSelectionVersion !== 1 || !agent?.defaultTier) {
    return { tier: '', engineId: '', modelId: '', voiceId: '' };
  }
  return {
    tier: agent.defaultTier,
    profileRevision: settings.profileRevision,
    engineId: settings.engineId || '',
    modelId: settings.modelId || '',
    voiceId: (agent.defaultTier === 'premium' ? settings.realtimeVoice : settings.voiceId) || '',
  };
}

function selectionKey(selection) {
  return [selection.tier, selection.tier === 'premium' ? '' : selection.profileRevision, selection.engineId, selection.modelId, selection.voiceId].join('|');
}

/**
 * Regional Indian and International spoken languages.
 */
export const EXTENDED_LANGUAGES = [
  {
    code: 'te-IN',
    name: 'Telugu',
    nativeName: 'తెలుగు',
    flag: '🇮🇳',
    badge: 'Native Neural',
    sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?',
  },
  {
    code: 'en-IN',
    name: 'English (India)',
    nativeName: 'Indian English',
    flag: '🇮🇳',
    badge: 'Localized Accent',
    sampleText: 'Hello. How can I help you today?',
  },
  {
    code: 'hi-IN',
    name: 'Hindi',
    nativeName: 'हिन्दी',
    flag: '🇮🇳',
    badge: 'Regional Voices',
    sampleText: 'नमस्ते। मैं आपकी कैसे मदद कर सकता हूँ?',
  },
  {
    code: 'ta-IN',
    name: 'Tamil',
    nativeName: 'தமிழ்',
    flag: '🇮🇳',
    badge: 'Regional Dravidian',
    sampleText: 'வணக்கம். உங்களுக்கு எப்படி உதவலாம்?',
  },
  {
    code: 'kn-IN',
    name: 'Kannada',
    nativeName: 'ಕನ್ನಡ',
    flag: '🇮🇳',
    badge: 'Multilingual Voice',
    sampleText: 'ನಮಸ್ಕಾರ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?',
  },
  {
    code: 'en-GB',
    name: 'English (UK)',
    nativeName: 'British English',
    flag: '🇬🇧',
    badge: 'RP Accent',
    sampleText: 'Hello. Thank you for calling. How may I assist you today?',
  },
  {
    code: 'en-US',
    name: 'English (US)',
    nativeName: 'American English',
    flag: '🇺🇸',
    badge: 'General American',
    sampleText: 'Hello. Thank you for calling. How can I help you today?',
  },
];

/**
 * Streamlined, high-density Voice & Language Studio.
 * Eliminates bulky cards in favor of a sleek, compact roster where all voices are visible simultaneously.
 */
export function AgentVoicePanel({
  formData,
  setFormData,
  agent = null,
  voiceStackProfiles = [],
  voiceStackCatalogLoading = false,
  voiceStackCatalogError = null,
  voiceCatalogLoading = false,
  onRetryVoiceStackCatalog,
  onRetryVoiceCatalog,
  onSaveVoiceStackSelection,
  onReloadVoiceStackSettings,
  onVoiceStackReadyChange,
  phoneVoices = [],
  activeVoiceProvider = 'openai',
  defaultVoiceId = 'te-in-csagent-5',
  voiceCatalogError = null,
  stackLabel = 'Enterprise Voice Network',
  onOpenTestCall,
  isAdmin = false,
}) {
  const storedVoiceId = String(
    formData?.voice?.realtimeVoice || formData?.voice?.voiceId || 'marin'
  ).toLowerCase();
  const currentVoiceId =
    activeVoiceProvider === 'gemini'
      ? String(
          phoneVoices.find(
            (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === storedVoiceId
          )?.id || defaultVoiceId || 'te-in-csagent-5'
        ).toLowerCase()
      : storedVoiceId;
  const currentLanguage =
    formData?.language ||
    (Array.isArray(formData?.languages) && formData.languages[0]) ||
    'te-IN';
  const [draftSelection, setDraftSelection] = useState(() => selectionFromAgent(agent));
  const [isSavingStackSelection, setIsSavingStackSelection] = useState(false);
  const [stackSelectionError, setStackSelectionError] = useState(null);
  const [stackSelectionNotice, setStackSelectionNotice] = useState(null);
  const [stackSelectionConflict, setStackSelectionConflict] = useState(false);
  const [previewRetry, setPreviewRetry] = useState(0);
  const [previewError, setPreviewError] = useState(false);
  const agentIdRef = useRef(agent?.id);
  const savedSelection = useMemo(() => selectionFromAgent(agent), [
    agent?.id,
    agent?.defaultTier,
    agent?.voiceSettings?.stackSelectionVersion,
    agent?.voiceSettings?.profileRevision,
    agent?.voiceSettings?.engineId,
    agent?.voiceSettings?.modelId,
    agent?.voiceSettings?.voiceId,
    agent?.voiceSettings?.realtimeVoice,
  ]);
  const savedSelectionRevision = Number.isSafeInteger(agent?.voiceRevision) ? agent.voiceRevision : 0;
  const savedSelectionStateKey = `${selectionKey(savedSelection)}|${savedSelectionRevision}`;
  const isStackOptedIn = agent?.voiceSettings?.stackSelectionVersion === 1;
  const catalogStackProfiles = Array.isArray(voiceStackProfiles)
    ? voiceStackProfiles.filter((profile) => profile?.tier && profile?.ready && profile?.enabled !== false && !profile?.blockers?.some(b => b.code === 'profile_not_available'))
    : [];
  const [isRefreshingVoiceData, setIsRefreshingVoiceData] = useState(false);

  const handleRefreshAllVoiceData = useCallback(async () => {
    if (isRefreshingVoiceData) return;
    setIsRefreshingVoiceData(true);
    try {
      await Promise.allSettled([
        onRetryVoiceStackCatalog ? onRetryVoiceStackCatalog() : Promise.resolve(),
        onRetryVoiceCatalog ? onRetryVoiceCatalog() : Promise.resolve(),
        onReloadVoiceStackSettings ? onReloadVoiceStackSettings() : Promise.resolve(),
      ]);
      showToast?.('success', 'Voice stacks and catalog refreshed.');
    } catch {
      showToast?.('error', 'Failed to refresh voice data.');
    } finally {
      setTimeout(() => setIsRefreshingVoiceData(false), 500);
    }
  }, [isRefreshingVoiceData, onRetryVoiceStackCatalog, onRetryVoiceCatalog, onReloadVoiceStackSettings]);
  const selectableStackProfiles = useMemo(
    () =>
      voiceStackProfiles
        .filter((profile) => isSelectableProfile(profile, currentLanguage)),
    [voiceStackProfiles, currentLanguage]
  );
  const currentStackProfile = selectableStackProfiles.find(
    (profile) => profile.tier === draftSelection?.tier
  );
  const currentStackEngines = useMemo(
    () => publicEngines(currentStackProfile, currentLanguage),
    [currentStackProfile, currentLanguage]
  );
  const currentStackEngine = currentStackEngines.find(
    (engine) => engine.id === draftSelection?.engineId
  );
  const currentStackModel = currentStackEngine?.models.find(
    (model) => model.id === draftSelection?.modelId
  );
  const currentStackVoice = currentStackModel?.voices.find(
    (voice) => voice.id === draftSelection?.voiceId
  );
  const savedProfile = selectableStackProfiles.find((profile) => profile.tier === savedSelection.tier);
  const savedEngine = publicEngines(savedProfile, currentLanguage)
    .find((engine) => engine.id === savedSelection.engineId);
  const savedModel = savedEngine?.models.find((model) => model.id === savedSelection.modelId);
  const savedVoice = savedModel?.voices.find((voice) => voice.id === savedSelection.voiceId);
  const hasUnsavedStackSelection = selectionKey(savedSelection) !== selectionKey({
    ...draftSelection,
    profileRevision: currentStackProfile?.profileRevision,
  });
  const persistedLanguage =
    (Array.isArray(agent?.languages) ? agent.languages[0] : null) ||
    agent?.language ||
    currentLanguage;
  const stackLanguageNeedsSave = currentLanguage !== persistedLanguage;
  const canSaveStackSelection = Boolean(
    onSaveVoiceStackSelection &&
      hasUnsavedStackSelection &&
      currentStackProfile &&
      formatRetailRate(currentStackProfile.retailRate) &&
      (currentStackProfile.tier === 'premium' || currentStackVoice) &&
      !stackLanguageNeedsSave &&
      !voiceStackCatalogLoading
  );
  const showExistingLiveVoiceControls =
    draftSelection?.tier === 'premium' ||
    (!isStackOptedIn && !draftSelection?.tier);

  const voiceStackReady = !isSavingStackSelection && !hasUnsavedStackSelection &&
    !stackLanguageNeedsSave && !stackSelectionError && !stackSelectionConflict;
  useEffect(() => {
    onVoiceStackReadyChange?.(Boolean(voiceStackReady));
  }, [onVoiceStackReadyChange, voiceStackReady]);

  useEffect(() => {
    if (!stackSelectionConflict || agentIdRef.current !== agent?.id) setDraftSelection(savedSelection);
    if (agentIdRef.current !== agent?.id) {
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      setStackSelectionConflict(false);
      setPreviewError(false);
      agentIdRef.current = agent?.id;
    }
  }, [agent?.id, savedSelectionStateKey]);

  const handleStackLanguageChange = (language) => {
    if (language === currentLanguage) return;
    setFormData((current) => ({
      ...current,
      language,
      languages: [language],
      voice: { ...current.voice, language },
    }));
    setDraftSelection((current) => ({ ...current, engineId: '', modelId: '', voiceId: '' }));
    setStackSelectionError(null);
    setStackSelectionNotice(null);
  };

  const confirmStackSave = useCallback((result) => {
    if (result?.conflict) {
      setStackSelectionConflict(true);
      setStackSelectionError(
        'Another editor saved newer voice settings. Your choice was not applied. Reload the saved settings before continuing.'
      );
      return false;
    }
    if (result?.languageNeedsSave) {
      setStackSelectionError('Save the language change before applying this voice setup.');
      return false;
    }
    if (result?.savedButUnconfirmed) {
      setStackSelectionConflict(true);
      setStackSelectionError('The save could not be confirmed. Reload the saved settings before trying again.');
      return false;
    }
    if (result?.error || !result?.agent) {
      setStackSelectionError(typeof result?.error === 'string'
        ? result.error
        : 'Voice setup could not be saved. Your saved choice is unchanged. Try again.');
      return false;
    }
    setDraftSelection(selectionFromAgent(result.agent));
    setStackSelectionConflict(false);
    setStackSelectionNotice('Voice setup saved. New calls will use this setting.');
    return true;
  }, []);

  const handleSaveStackSelection = async () => {
    if (!canSaveStackSelection || isSavingStackSelection) return;
    setIsSavingStackSelection(true);
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    try {
      confirmStackSave(await onSaveVoiceStackSelection({
        tier: draftSelection.tier,
        ...(draftSelection.tier === 'premium'
          ? { realtimeVoice: draftSelection.voiceId }
          : {
              profileRevision: currentStackProfile?.profileRevision,
              engineId: draftSelection.engineId,
              modelId: draftSelection.modelId,
              voiceId: draftSelection.voiceId,
            }),
      }));
    } catch {
      setStackSelectionError('Voice setup could not be saved. Your saved choice is unchanged. Try again.');
    } finally {
      setIsSavingStackSelection(false);
    }
  };

  const handleReloadStackSettings = async () => {
    if (!onReloadVoiceStackSettings) return;
    setIsSavingStackSelection(true);
    const latest = await onReloadVoiceStackSettings();
    setIsSavingStackSelection(false);
    if (!latest) {
      setStackSelectionError('Saved settings could not be reloaded. Try again.');
      return;
    }
    setDraftSelection(selectionFromAgent(latest));
    setStackSelectionError(null);
    setStackSelectionConflict(false);
    setStackSelectionNotice('Saved voice settings reloaded.');
  };
  const currentSpeed = formData?.voice?.speed ?? 1.0;
  const currentPitch = formData?.voice?.pitch ?? 0.0;
  const currentStability = formData?.voice?.stability ?? 0.75;

  const [playingVoiceId, setPlayingVoiceId] = useState(null);
  const [playingType, setPlayingType] = useState(null); // 'sample'
  const [audioError, setAudioError] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [genderFilter, setGenderFilter] = useState('all');
  const [showAcousticControls, setShowAcousticControls] = useState(false);

  // Merge server phone voices with catalog
  const displayVoices = useMemo(() => {
    const langPrefix = String(currentLanguage || 'te-IN').split('-')[0].toLowerCase();

    const localizeVoice = (v) => {
      const vid = String(v.providerVoiceId || v.name || v.label || v.id || '')
        .toLowerCase()
        .replace(/^voice-/, '')
        .trim();
      const localizedSampleUrl = `/audio/voxly/samples/${vid}_${langPrefix}.wav`;
      const baseSampleUrl = v.sampleUrl || `/audio/voxly/samples/${vid}.wav`;
      const localizedSampleText =
        v.sampleText ||
        EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
        'Hello. Thank you for calling. How can I help you today?';
      const cleanGender = v.gender === 'neutral' ? 'female' : (v.gender || 'female');
      return {
        ...v,
        gender: cleanGender,
        sampleUrl: localizedSampleUrl,
        fallbackUrl: baseSampleUrl,
        sampleText: localizedSampleText,
      };
    };

    if (activeVoiceProvider === 'gemini') {
      const liveVoices = phoneVoices
        .filter((voice) => voice.provider === 'gemini')
        .map((voice) => ({
          ...voice,
          name: voice.label || voice.geminiVoice || voice.id,
          gender: voice.gender === 'neutral' ? 'female' : (voice.gender || 'female'),
          sampleUrl: voice.sampleUrl || `/audio/voxly/samples/${voice.id?.toLowerCase()}.wav`,
          sampleText:
            voice.sampleText ||
            EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
            'Hello. Thank you for calling. How can I help you today?',
        }));

      // Multilingual Gemini Live voices (Zephyr, Aoede, Kore, Leda, Puck, Charon, Fenrir, Orus, etc.)
      const multilingualVoices = liveVoices.filter((voice) => !voice.languageCode);
      // Regional dialect voices matching current language (e.g. te-in-csagent-5 for te-IN)
      const localeVoices = liveVoices.filter((voice) => voice.languageCode === currentLanguage);

      if (multilingualVoices.length || localeVoices.length) {
        // Core Gemini 3.8 Live voices: Zephyr first, followed by the rest of the core roster
        const CORE_ORDER = ['zephyr', 'aoede', 'kore', 'leda', 'puck', 'charon', 'fenrir', 'orus'];
        const combined = [...multilingualVoices, ...localeVoices];
        const seen = new Set();
        const deduped = [];
        // First add core voices in order
        for (const cid of CORE_ORDER) {
          const match = combined.find((v) => String(v.id).toLowerCase() === cid);
          if (match && !seen.has(String(match.id).toLowerCase())) {
            seen.add(String(match.id).toLowerCase());
            deduped.push(match);
          }
        }
        // Then add locale-specific presets for current language
        for (const v of localeVoices) {
          const idKey = String(v.id).toLowerCase();
          if (!seen.has(idKey)) {
            seen.add(idKey);
            deduped.push(v);
          }
        }
        // Then add any remaining voices
        for (const v of combined) {
          const idKey = String(v.id).toLowerCase();
          if (!seen.has(idKey)) {
            seen.add(idKey);
            deduped.push(v);
          }
        }
        return deduped.map((v, idx) => {
          const loc = localizeVoice(v);
          return {
            ...loc,
            name: `Voice ${idx + 1}`,
            label: `Voice ${idx + 1}`,
          };
        });
      }
      if (liveVoices.length) {
        return liveVoices.map((v, idx) => {
          const loc = localizeVoice(v);
          return {
            ...loc,
            name: `Voice ${idx + 1}`,
            label: `Voice ${idx + 1}`,
          };
        });
      }
    }
    return VOICE_CATALOG.map((catVoice, idx) => {
      const match = phoneVoices.find(
        (pv) =>
          pv.id?.toLowerCase() === catVoice.id.toLowerCase() ||
          pv.name?.toLowerCase() === catVoice.name.toLowerCase()
      );
      const merged = match
        ? {
            ...catVoice,
            name: `Voice ${idx + 1}`,
            label: `Voice ${idx + 1}`,
            category: match.category || catVoice.category,
            useCase: match.useCase || catVoice.useCase,
            tone: match.tone || catVoice.tone,
            gender: match.gender && match.gender !== 'neutral' ? match.gender : catVoice.gender,
          }
        : {
            ...catVoice,
            name: `Voice ${idx + 1}`,
            label: `Voice ${idx + 1}`,
          };
      return localizeVoice(merged);
    });
  }, [phoneVoices, activeVoiceProvider, currentLanguage, currentVoiceId]);

  const voiceCategoryCounts = useMemo(() => {
    const isConv = (v) => v.category === 'conversational' || v.category === 'support' || v.category === 'care';
    const isPromo = (v) => v.category === 'promotional' || v.category === 'sales' || v.category === 'operations';
    return {
      all: displayVoices.length,
      conversational: displayVoices.filter(isConv).length,
      promotional: displayVoices.filter(isPromo).length,
    };
  }, [displayVoices]);

  // Filtered voice list
  const filteredVoices = useMemo(() => {
    return displayVoices.filter((v) => {
      if (activeCategory !== 'all') {
        const cat = v.category;
        if (activeCategory === 'conversational') {
          if (cat !== 'conversational' && cat !== 'support' && cat !== 'care') return false;
        } else if (activeCategory === 'promotional') {
          if (cat !== 'promotional' && cat !== 'sales' && cat !== 'operations') return false;
        } else if (cat !== activeCategory) {
          return false;
        }
      }
      if (genderFilter !== 'all' && v.gender !== genderFilter) return false;
      return true;
    });
  }, [displayVoices, activeCategory, genderFilter]);

  // Active voice metadata
  const activeVoice = useMemo(() => {
    return (
      displayVoices.find((v) => v.id === currentVoiceId) ||
      displayVoices[0] ||
      VOICE_CATALOG[0]
    );
  }, [displayVoices, currentVoiceId]);

  // Active language metadata
  const activeLanguage = useMemo(() => {
    return (
      EXTENDED_LANGUAGES.find((l) => l.code === currentLanguage) ||
      EXTENDED_LANGUAGES[0]
    );
  }, [currentLanguage]);

  // Computed voices for each tier for the active language
  const tierVoicesMap = useMemo(() => {
    const map = {};
    for (const profile of catalogStackProfiles) {
      if (!profile?.tier) continue;
      if (profile.tier === 'premium') {
        map.premium = displayVoices.map((v, idx) => ({
          ...v,
          name: `Voice ${idx + 1}`,
          label: `Voice ${idx + 1}`,
        }));
      } else {
        const engines = publicEngines(profile, currentLanguage);
        const voices = [];
        for (const engine of engines) {
          for (const model of engine.models || []) {
            for (const v of model.voices || []) {
              const voiceNumber = voices.length + 1;
              voices.push({
                ...v,
                tier: profile.tier,
                profileRevision: profile.profileRevision,
                engineId: engine.id,
                engineLabel: engine.label,
                modelId: model.id,
                modelLabel: model.label,
                audioStreaming: model.audioStreaming,
                name: `Voice ${voiceNumber}`,
                label: `Voice ${voiceNumber}`,
              });
            }
          }
        }
        map[profile.tier] = voices;
      }
    }
    return map;
  }, [catalogStackProfiles, currentLanguage, displayVoices]);

  // Audio sample playback
  const handlePlayVoiceSample = useCallback(
    async (voice, tierParam = null) => {
      setAudioError(null);

      // Toggle off if currently playing
      if (playingVoiceId === voice.id && playingType === 'sample') {
        voiceAgent.stopTTS();
        setPlayingVoiceId(null);
        setPlayingType(null);
        return;
      }

      voiceAgent.stopTTS();
      setPlayingVoiceId(voice.id);
      setPlayingType('sample');

      const targetTier = tierParam || draftSelection?.tier || (isStackOptedIn ? agent?.defaultTier : 'premium');
      const langPrefix = String(currentLanguage || 'te-IN').split('-')[0].toLowerCase();
      const vid = String(voice.providerVoiceId || voice.name || voice.label || voice.id || '')
        .toLowerCase()
        .replace(/^voice-/, '')
        .trim();
      const localizedSampleUrl = `/audio/voxly/samples/${vid}_${langPrefix}.wav`;
      const baseSampleUrl = voice.fallbackUrl || `/audio/voxly/samples/${vid}.wav`;
      const audioUrl = voice.sampleUrl || localizedSampleUrl;
      const fallbackUrl = baseSampleUrl;
      const langMeta = EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage);
      const previewText =
        langMeta?.sampleText ||
        voice.sampleText ||
        'Hello. Thank you for calling. How can I help you today?';

      try {
        const result = await api.telephony.previewVoice({
          text: previewText,
          voiceId: voice.id,
          language: currentLanguage,
          speed: currentSpeed,
          tier: targetTier,
        });
        if (result?.blob) {
          const played = await voiceAgent.playAudioBuffer(
            result.blob,
            () => {
              setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
              setPlayingType((curr) => (curr === 'sample' ? null : curr));
            },
            () => {
              setPlayingVoiceId(voice.id);
              setPlayingType('sample');
            }
          );
          if (played) return;
        }
      } catch (e) {
        const msg = String(e?.message || '').trim();
        if (msg && !msg.includes('Failed to fetch')) {
          setPlayingVoiceId(null);
          setPlayingType(null);
          setAudioError(msg);
          return;
        }
      }

      try {
        voiceAgent.playAudioClip(
          audioUrl,
          () => {
            setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
            setPlayingType((curr) => (curr === 'sample' ? null : curr));
          },
          () => {
            setPlayingVoiceId(voice.id);
            setPlayingType('sample');
          },
          {
            fallbackUrl,
            fallbackText: previewText,
          }
        );
      } catch (e) {
        setPlayingVoiceId(null);
        setPlayingType(null);
        setAudioError(
          String(e?.message || '').trim() ||
            'Could not play the voice sample. Check the audio output device.'
        );
      }
    },
    [playingVoiceId, playingType, currentLanguage, currentSpeed, draftSelection?.tier, isStackOptedIn, agent?.defaultTier]
  );

  const handleStopAudio = useCallback(() => {
    voiceAgent.stopTTS();
    setPlayingVoiceId(null);
    setPlayingType(null);
  }, []);

  // Live voice selection
  const handleSelectVoice = useCallback(
    (voice) => {
      setDraftSelection({
        tier: 'premium',
        profileRevision: 1,
        engineId: '',
        modelId: '',
        voiceId: voice.id,
      });
      setFormData((prev) => ({
        ...prev,
        defaultTier: 'premium',
        voice: {
          ...prev.voice,
          provider: 'phone_ai',
          realtimeVoice: voice.id,
          voiceId: voice.id,
          voiceName: voice.name || voice.id,
          language: currentLanguage,
        },
        voiceSettings: {
          stackSelectionVersion: 1,
          realtimeVoice: voice.id,
        },
      }));
      showToast(`Speaking voice set to ${voice.name} (${voice.tone})`, 'info');
    },
    [currentLanguage, setFormData]
  );

  // Stack Tier Voice selection (automatically applies voice and saves tier setup)
  const handleSelectTierVoice = useCallback(
    async (profile, voice) => {
      if (isSavingStackSelection || stackSelectionConflict) return;
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      const isPremium = profile.tier === 'premium';
      const newSelection = {
        tier: profile.tier,
        profileRevision: isPremium ? undefined : profile.profileRevision,
        engineId: isPremium ? '' : voice.engineId,
        modelId: isPremium ? '' : voice.modelId,
        voiceId: voice.id,
      };
      setDraftSelection(newSelection);
      setIsSavingStackSelection(true);
      try {
        const result = await onSaveVoiceStackSelection?.(isPremium
          ? { tier: 'premium', realtimeVoice: voice.id }
          : newSelection);
        if (!confirmStackSave(result)) return;
        if (isPremium) {
          handleSelectVoice(voice);
          return;
        }
        setFormData((prev) => ({
          ...prev,
          defaultTier: profile.tier,
          voice: {
            ...prev.voice,
            voiceId: voice.id,
            label: voice.label || voice.id,
            language: currentLanguage,
          },
          voiceSettings: {
            stackSelectionVersion: 1,
            profileRevision: profile.profileRevision,
            engineId: voice.engineId,
            modelId: voice.modelId,
            voiceId: voice.id,
          },
        }));
      } catch {
        setStackSelectionError('Voice setup could not be saved. Your saved choice is unchanged. Try again.');
      } finally {
        setIsSavingStackSelection(false);
      }
    },
    [currentLanguage, handleSelectVoice, onSaveVoiceStackSelection, setFormData, isSavingStackSelection, stackSelectionConflict, confirmStackSave]
  );

  const handleStackTierChange = useCallback(
    (tier) => {
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      if (tier === savedSelection.tier) {
        setDraftSelection(savedSelection);
        return;
      }
      const prof = selectableStackProfiles.find((p) => p.tier === tier);
      if (tier === 'premium') {
        const liveVoice = displayVoices[0] || { id: 'zephyr', name: 'Zephyr' };
        setDraftSelection({
          tier: 'premium',
          profileRevision: 1,
          engineId: '',
          modelId: '',
          voiceId: liveVoice.id,
        });
        setFormData((prev) => ({
          ...prev,
          defaultTier: 'premium',
          voice: {
            ...prev.voice,
            realtimeVoice: liveVoice.id,
            voiceId: liveVoice.id,
            voiceName: liveVoice.name || liveVoice.id,
          },
          voiceSettings: {
            stackSelectionVersion: 1,
            realtimeVoice: liveVoice.id,
          },
        }));
      } else if (prof) {
        const engines = publicEngines(prof, currentLanguage);
        const firstVoice = engines[0]?.models?.[0]?.voices?.[0];
        if (firstVoice) {
          setDraftSelection({
            tier,
            profileRevision: prof.profileRevision,
            engineId: engines[0].id,
            modelId: engines[0].models[0].id,
            voiceId: firstVoice.id,
          });
          setFormData((prev) => ({
            ...prev,
            defaultTier: tier,
            voice: {
              ...prev.voice,
              voiceId: firstVoice.id,
              label: firstVoice.label || firstVoice.id,
              language: currentLanguage,
            },
            voiceSettings: {
              stackSelectionVersion: 1,
              profileRevision: prof.profileRevision,
              engineId: engines[0].id,
              modelId: engines[0].models[0].id,
              voiceId: firstVoice.id,
            },
          }));
        } else {
          setDraftSelection({ tier, engineId: '', modelId: '', voiceId: '' });
        }
      } else {
        setDraftSelection({ tier, engineId: '', modelId: '', voiceId: '' });
      }
    },
    [savedSelection, selectableStackProfiles, currentLanguage, displayVoices, setFormData]
  );

  // Language selection
  const handleSelectLanguage = useCallback(
    (langCode) => {
      setStackSelectionError(null);
      setStackSelectionNotice(null);

      const currentGeminiVoice = phoneVoices.find(
        (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === currentVoiceId
      );
      const nativeDefault = phoneVoices.find(
        (voice) =>
          voice.provider === 'gemini' &&
          voice.languageCode === langCode &&
          voice.defaultForLanguage === true
      );
      const multilingualDefault =
        phoneVoices.find(
          (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === 'zephyr'
        ) ||
        phoneVoices.find(
          (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === 'puck'
        );
      const voiceAlreadyMatches = currentGeminiVoice?.languageCode === langCode;
      const nextGeminiVoice =
        activeVoiceProvider === 'gemini' && !voiceAlreadyMatches
          ? nativeDefault || (currentGeminiVoice?.languageCode ? multilingualDefault : null)
          : null;

      setFormData((prev) => ({
        ...prev,
        language: langCode,
        languages: [langCode],
        voice: {
          ...prev.voice,
          language: langCode,
          ...(nextGeminiVoice
            ? {
                realtimeVoice: nextGeminiVoice.id,
                voiceId: nextGeminiVoice.id,
                voiceName: nextGeminiVoice.label || nextGeminiVoice.id,
              }
            : {}),
        },
      }));

      // In composed tier, update draftSelection to a valid voice for the new language
      if (draftSelection?.tier && draftSelection.tier !== 'premium') {
        const prof = selectableStackProfiles.find((p) => p.tier === draftSelection.tier);
        const engines = publicEngines(prof, langCode);
        const firstVoice = engines[0]?.models?.[0]?.voices?.[0];
        if (firstVoice) {
          setDraftSelection((curr) => ({
            ...curr,
            engineId: engines[0].id,
            modelId: engines[0].models[0].id,
            voiceId: firstVoice.id,
          }));
          setFormData((prev) => ({
            ...prev,
            voice: {
              ...prev.voice,
              voiceId: firstVoice.id,
              label: firstVoice.label || firstVoice.id,
              language: langCode,
            },
            voiceSettings: {
              stackSelectionVersion: 1,
              profileRevision: prof?.profileRevision || 1,
              engineId: engines[0].id,
              modelId: engines[0].models[0].id,
              voiceId: firstVoice.id,
            },
          }));
        } else {
          setDraftSelection((curr) => ({ ...curr, engineId: '', modelId: '', voiceId: '' }));
        }
      }

      const lMeta = EXTENDED_LANGUAGES.find((l) => l.code === langCode);
      showToast(`Language updated to ${lMeta?.name || langCode}`, 'info');
    },
    [phoneVoices, currentVoiceId, activeVoiceProvider, draftSelection?.tier, selectableStackProfiles, setFormData]
  );



  // Clean up audio on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
    };
  }, []);

  return (
    <div className="space-y-4" data-testid="agent-voice-panel">
      {/* 1. Primary Spoken Language & Accent Card */}
      <div
        className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-2.5"
        data-testid="language-selection-card"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Languages className="w-4 h-4 text-[#6344E7]" />
            <span className="text-xs font-bold text-[#0F0E17]">
              Primary Spoken Language &amp; Accent
            </span>
          </div>
          <span className="text-[11px] font-medium text-[#6344E7]">
            Active: {activeLanguage.name} ({activeLanguage.code})
          </span>
        </div>

        {/* Compact Horizontal Pill Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
          {EXTENDED_LANGUAGES.map((lang) => {
            const isSelected = currentLanguage === lang.code;
            return (
              <button
                key={lang.code}
                type="button"
                data-testid={`language-card-${lang.code}`}
                disabled={isSavingStackSelection || stackSelectionConflict}
                aria-pressed={isSelected}
                onClick={() => handleSelectLanguage(lang.code)}
                className={`flex flex-col items-center justify-center p-2 rounded-lg text-center transition-all ${
                  isSelected
                    ? 'bg-[#6344E7]/10 border-2 border-[#6344E7] text-[#0F0E17] shadow-xs'
                    : 'bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E] hover:border-[#6344E7]/40 hover:bg-white'
                }`}
              >
                <div className="flex items-center gap-1">
                  <span className="text-sm">{lang.flag}</span>
                  <span className="text-[11px] font-bold text-[#0F0E17]">
                    {lang.nativeName}
                  </span>
                </div>
                <span className="text-[10px] text-[#524E5E] truncate max-w-full">
                  {lang.name}
                </span>
                <span className="text-[9px] text-[#8C879A] mt-0.5 uppercase tracking-wider">
                  {lang.code}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <section
        className="rounded-xl border border-[#E4E2EB] bg-white p-4 shadow-xs space-y-4"
        data-testid="voice-stack-selector"
        aria-busy={voiceStackCatalogLoading}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-[#0F0E17]">Voice setup</h2>
            <p className="mt-1 text-xs text-[#524E5E]">
              Saved setup:{' '}
              <strong className="text-[#0F0E17]">
                {isStackOptedIn && agent?.defaultTier
                  ? (STACK_TIER_LABELS[agent.defaultTier] || savedProfile?.label || agent.defaultTier)
                  : 'Current voice configuration'}
              </strong>
              {isStackOptedIn && savedVoice ? ` · ${savedVoice.label}` : ''}
            </p>
            <p className="mt-1 text-[11px] text-[#716C7F]">
              Saved changes apply to new calls. Calls already in progress keep their current setup.
            </p>
          </div>
          {isStackOptedIn && agent?.defaultTier === 'premium' && (
            <span className="rounded-full border border-[#6344E7]/20 bg-[#6344E7]/5 px-2.5 py-1 text-[11px] font-semibold text-[#5233D6]">
              Live voice controls below
            </span>
          )}
        </div>

        {voiceStackCatalogLoading && (
          <p className="text-xs text-[#716C7F]" role="status" data-testid="voice-stack-loading">
            Loading approved voice options…
          </p>
        )}
        {voiceStackCatalogError && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert">
            <span>{voiceStackCatalogError}</span>
            <button
              type="button"
              onClick={onRetryVoiceStackCatalog}
              disabled={voiceStackCatalogLoading}
              className="rounded-md border border-red-300 px-2.5 py-1 font-semibold hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400 disabled:opacity-50"
              data-testid="voice-stack-catalog-retry"
            >
              Retry
            </button>
          </div>
        )}
        {!voiceStackCatalogLoading && !voiceStackCatalogError && !voiceCatalogLoading && selectableStackProfiles.length === 0 && (
          <p className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2.5 text-xs text-[#524E5E]" data-testid="voice-stack-empty">
            No approved voice setup is available for this language yet. Your current saved setup is unchanged.
          </p>
        )}

        {/* 3 Columns for the Stacks with Scrollable Voices */}
        {catalogStackProfiles.length > 0 && (
          <fieldset className="space-y-3" disabled={isSavingStackSelection || voiceStackCatalogLoading}>
            <div className="flex items-center justify-between mb-2">
              <legend className="text-xs font-semibold text-[#0F0E17]">
                Voice Stacks &amp; Tier Architecture
              </legend>
              <button
                type="button"
                onClick={handleRefreshAllVoiceData}
                disabled={isRefreshingVoiceData || voiceStackCatalogLoading}
                className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold text-[#6344E7] hover:text-[#5233D6] bg-[#6344E7]/5 hover:bg-[#6344E7]/10 rounded-lg border border-[#6344E7]/20 transition-all cursor-pointer disabled:opacity-50"
                title="Refresh Voice Stacks from backend"
                data-testid="refresh-voice-stacks-btn"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingVoiceData || voiceStackCatalogLoading ? 'animate-spin' : ''}`} />
                <span>{isRefreshingVoiceData || voiceStackCatalogLoading ? 'Refreshing…' : 'Refresh Stacks'}</span>
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {catalogStackProfiles.map((profile) => {
                const isSelectedTier = draftSelection?.tier === profile.tier;
                const ready = isSelectableProfile(profile, currentLanguage);
                const voices = tierVoicesMap[profile.tier] || [];

                return (
                  <div
                    key={profile.tier}
                    className={`flex flex-col rounded-xl border transition-all ${
                      isSelectedTier
                        ? 'border-[#6344E7] bg-white ring-2 ring-[#6344E7]/20 shadow-xs'
                        : 'border-[#E4E2EB] bg-white hover:border-[#B9B4C8]'
                    } ${!ready ? 'opacity-70' : ''}`}
                  >
                    {/* Column Header */}
                    <div className="p-3.5 border-b border-[#F0EEF6] bg-[#FAF9FD]/50 rounded-t-xl">
                      <div className="flex items-start justify-between gap-2">
                        <label className="flex items-center gap-2 cursor-pointer select-none">
                          <input
                            type="radio"
                            name={`voice-stack-tier-${agent?.id || 'agent'}`}
                            value={profile.tier}
                            checked={isSelectedTier}
                            disabled={!ready || isSavingStackSelection || stackSelectionConflict}
                            aria-describedby={`voice-stack-tier-status-${profile.tier}`}
                            onChange={() => handleStackTierChange(profile.tier)}
                            className="mt-0.5 accent-[#6344E7]"
                            data-testid={`voice-stack-tier-${profile.tier}`}
                          />
                          <div>
                            <span className="block text-xs font-bold text-[#0F0E17]">
                              {STACK_TIER_LABELS[profile.tier] || profile.label || profile.tier}
                            </span>
                            <span className="text-[10px] text-[#716C7F]">
                              {profile.tier === 'low'
                                ? 'Economical Composed Voice'
                                : profile.tier === 'medium'
                                ? 'Standard Regional Expressive'
                                : profile.tier === 'premium'
                                ? 'Flagship Realtime Live'
                                : (profile.description || `${profile.label || 'Custom'} Composed Stack`)}
                            </span>
                          </div>
                        </label>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                            profile.tier === 'premium'
                              ? 'bg-[#6344E7]/10 text-[#6344E7] border-[#6344E7]/25'
                              : profile.tier === 'medium'
                              ? 'bg-blue-50 text-blue-700 border-blue-200'
                              : profile.tier === 'low'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-purple-50 text-purple-700 border-purple-200'
                          }`}
                        >
                          {profile.tier === 'low'
                            ? 'Economical'
                            : profile.tier === 'medium'
                            ? 'Standard'
                            : profile.tier === 'premium'
                            ? 'Flagship'
                            : (profile.label || 'Custom')}
                        </span>
                      </div>
                      <div
                        id={`voice-stack-tier-status-${profile.tier}`}
                        className="mt-2 text-[11px] text-[#524E5E] font-medium"
                      >
                        {ready
                          ? `Approved retail rate: ${formatRetailRate(profile.retailRate)}`
                          : 'Unavailable for this language until setup is approved.'}
                      </div>
                    </div>

                    {/* Column Body: Scrollable Voice Section */}
                    <div className="p-3 flex-1 flex flex-col min-h-0">
                      <div className="flex items-center justify-between text-[11px] font-semibold text-[#524E5E] mb-2">
                        <span>Voices for {activeLanguage.name}</span>
                        <span className="text-[10px] text-[#8C879A] font-normal">
                          {voices.length} {voices.length === 1 ? 'voice' : 'voices'}
                        </span>
                      </div>

                      <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1 divide-y divide-[#F0EEF6]">
                        {voices.length === 0 ? (
                          <div className="py-6 text-center text-xs text-[#8C879A] italic">
                            No approved voices available for {activeLanguage.name} in this tier.
                          </div>
                        ) : (
                          voices.map((v) => {
                            const isVoiceSelected =
                              profile.tier === 'premium'
                                ? (isSelectedTier || (!isStackOptedIn && !draftSelection?.tier)) &&
                                  (currentVoiceId === v.id || draftSelection?.voiceId === v.id)
                                : isSelectedTier &&
                                  draftSelection?.voiceId === v.id &&
                                  (v.engineId ? draftSelection?.engineId === v.engineId : true);
                            const isPlayingThis = playingVoiceId === v.id && playingType === 'sample';

                            return (
                              <div
                                key={`${profile.tier}-${v.engineId || ''}-${v.id}`}
                                onClick={() => ready && handleSelectTierVoice(profile, v)}
                                className={`flex items-center justify-between gap-2 p-2 rounded-lg transition-colors cursor-pointer select-none ${
                                  isVoiceSelected
                                    ? 'bg-[#6344E7]/10 border border-[#6344E7]/30'
                                    : 'hover:bg-[#FAF9FD]'
                                }`}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  {/* Play/Stop Button */}
                                  <button
                                    type="button"
                                    data-testid={profile.tier === 'premium' && showExistingLiveVoiceControls ? `voice-tier-play-btn-${v.id}` : `voice-play-btn-${v.id}`}
                                    aria-label={`Play preview for ${v.label || v.name}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handlePlayVoiceSample(v, profile.tier);
                                    }}
                                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all ${
                                      isPlayingThis
                                        ? 'bg-rose-600 text-white shadow-xs'
                                        : 'bg-[#6344E7]/10 text-[#6344E7] hover:bg-[#6344E7] hover:text-white'
                                    }`}
                                  >
                                    {isPlayingThis ? (
                                      <Square className="w-3 h-3 fill-current" />
                                    ) : (
                                      <Play className="w-3 h-3 fill-current ml-0.5" />
                                    )}
                                  </button>

                                  {/* Voice Name & Details */}
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <span className="text-xs font-bold text-[#0F0E17] truncate">
                                        {v.label || v.name}
                                      </span>
                                      {v.gender && (
                                        <span className="text-[9px] uppercase px-1 rounded bg-[#F0EEF6] text-[#524E5E] font-semibold">
                                          {v.gender}
                                        </span>
                                      )}
                                      {(v.tag === 'Indian' || v.accent?.includes('Indian') || v.label?.includes('Indian') || v.useCase?.includes('Indian')) && (
                                        <span className="text-[9px] px-1 py-0.2 rounded font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                          🇮🇳 Indian
                                        </span>
                                      )}
                                      {v.category && (
                                        <span className={`text-[9px] px-1 py-0.2 rounded font-medium ${
                                          v.category === 'sales'
                                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                            : v.category === 'operations'
                                            ? 'bg-purple-50 text-purple-700 border border-purple-200'
                                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                        }`}>
                                          {v.category.charAt(0).toUpperCase() + v.category.slice(1)}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-[10px] text-[#716C7F] truncate">
                                      {v.tone
                                        ? `${v.tone}${v.useCase ? ` · ${v.useCase}` : ''}`
                                        : profile.tier === 'premium'
                                        ? v.useCase || 'Live Neural'
                                        : v.modelLabel || v.engineLabel || 'Regional Voice'}
                                    </p>
                                  </div>
                                </div>

                                {/* Choose / Selected Action */}
                                <button
                                  type="button"
                                  data-testid={profile.tier === 'premium' && showExistingLiveVoiceControls ? `voice-tier-select-btn-${v.id}` : `voice-select-btn-${v.id}`}
                                  disabled={isSavingStackSelection || stackSelectionConflict}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleSelectTierVoice(profile, v);
                                  }}
                                  className={`shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition-all ${
                                    isVoiceSelected
                                      ? 'bg-[#6344E7] text-white shadow-2xs'
                                      : 'bg-[#FAF9FD] text-[#524E5E] hover:bg-[#6344E7]/15 hover:text-[#6344E7] border border-[#E4E2EB]'
                                  }`}
                                >
                                  {isSavingStackSelection && isVoiceSelected ? (
                                    <span>Saving…</span>
                                  ) : isVoiceSelected ? (
                                    <>
                                      <Check className="w-3 h-3 stroke-[3]" />
                                      <span>Selected</span>
                                    </>
                                  ) : (
                                    <span>Choose</span>
                                  )}
                                </button>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </fieldset>
        )}

        {/* Saved configuration indicator & status messages */}
        {isStackOptedIn && savedSelection.tier && STACK_TIER_LABELS[savedSelection.tier] && (
          <div className="mt-3 flex items-center justify-between border-t border-[#F0EEF6] pt-2.5">
            <p className="text-[11px] text-[#716C7F]">
              Saved configuration: <span className="font-semibold text-[#0F0E17]">{STACK_TIER_LABELS[savedSelection.tier]}</span>
              {savedVoice ? ` · ${savedVoice.label}` : ''}
            </p>
          </div>
        )}

        {stackSelectionError && (
          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert" data-testid="voice-stack-save-error">
            <span>{stackSelectionError}</span>
            {stackSelectionConflict && onReloadVoiceStackSettings && (
              <button
                type="button"
                onClick={handleReloadStackSettings}
                disabled={isSavingStackSelection}
                className="rounded-md border border-red-300 px-2.5 py-1 font-semibold hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400 disabled:opacity-50"
                data-testid="voice-stack-conflict-reload"
              >
                Reload saved settings
              </button>
            )}
          </div>
        )}
        {stackSelectionNotice && (
          <p className="mt-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" role="status" data-testid="voice-stack-save-status">
            {stackSelectionNotice}
          </p>
        )}
      </section>

      {showExistingLiveVoiceControls && (
        <>
      {/* 1. Header Bar: Compact Active Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[#6344E7]/10 flex items-center justify-center text-[#6344E7]">
            <Volume2 className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#0F0E17]">
                Voice &amp; Language Configuration
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[#FAF9FD] text-[#6344E7] border border-[#6344E7]/20">
                {draftSelection?.tier === 'premium' ? STACK_TIER_LABELS.premium : 'Current voice setup'}
              </span>
            </div>
            <p className="text-[11px] text-[#524E5E]">
              Selected: <strong className="text-[#0F0E17]">{activeVoice.name}</strong> ({activeVoice.tone}) · <strong className="text-[#0F0E17]">{activeLanguage.name}</strong> ({activeLanguage.code})
            </p>
          </div>
        </div>

        {/* Action Controls & Floating Playing Status */}
        <div className="flex items-center gap-2">
          {playingVoiceId && (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#6344E7]/10 text-[#6344E7] text-xs font-semibold animate-pulse border border-[#6344E7]/25"
              data-testid="voice-playing-indicator"
            >
              <div className="flex items-center gap-0.5 h-3">
                <span className="w-0.5 h-3 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-0.5 h-2 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-0.5 h-3.5 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span>
                Playing sample: {displayVoices.find((v) => v.id === playingVoiceId)?.name || playingVoiceId}
              </span>
              <button
                type="button"
                onClick={handleStopAudio}
                data-testid="stop-voice-audio-btn"
                className="ml-1 p-0.5 rounded hover:bg-[#6344E7]/20 text-[#6344E7]"
                title="Stop audio"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            </div>
          )}

          {onOpenTestCall && (
            <button
              type="button"
              onClick={onOpenTestCall}
              data-testid="voice-open-test-call-btn"
              disabled={!voiceStackReady}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#6344E7] hover:bg-[#5233D6] text-white shadow-xs transition-all cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              <span>Test Live Agent</span>
            </button>
          )}
        </div>
      </div>

      {audioError && (
        <div
          className="flex items-center gap-2 p-2.5 rounded-lg bg-amber-50 text-amber-800 text-xs border border-amber-200"
          data-testid="voice-preview-error"
          role="alert"
        >
          <Info className="w-4 h-4 shrink-0 text-amber-600" />
          <span>{audioError}</span>
        </div>
      )}

      {/* 2. Speaking Voices Showcase: Dense Roster List Format */}
      <div
        className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-3"
        data-testid="speaking-voice-showcase"
      >
        {voiceCatalogError && (
          <p className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2" role="alert">
            {voiceCatalogError}
          </p>
        )}
        {activeVoiceProvider === 'gemini' && ['hi-IN', 'te-IN'].includes(currentLanguage) && (
          <p
            className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
            data-testid="voice-localization-note"
          >
            {currentLanguage === 'te-IN' ? 'Telugu (India) choices include regional support, concierge, and technical voices.' : 'Hindi-specific choices are regional voices.'} Each voice is labeled with its accent; preview it before selecting.
          </p>
        )}
        {activeVoiceProvider === 'gemini' &&
          currentLanguage !== 'hi-IN' &&
          !phoneVoices.some(
            (voice) => voice.provider === 'gemini' && voice.languageCode === currentLanguage
          ) && (
            <p
              className="text-[11px] text-[#716C7F] bg-[#FAF9FD] border border-[#E4E2EB] rounded-lg px-3 py-2"
              data-testid="voice-localization-note"
            >
              This language has no dedicated regional voice in the current Gemini Live catalog. The multilingual voice follows the selected language instruction.
            </p>
          )}
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#F0EEF6]">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-[#6344E7]" />
            <span className="text-xs font-bold text-[#0F0E17]">
              Available Speaking Voices ({filteredVoices.length})
            </span>
            <button
              type="button"
              onClick={handleRefreshAllVoiceData}
              disabled={isRefreshingVoiceData || voiceCatalogLoading}
              className="flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium text-[#6344E7] hover:text-[#5233D6] bg-[#6344E7]/5 hover:bg-[#6344E7]/10 rounded-md border border-[#6344E7]/20 transition-all cursor-pointer ml-1 disabled:opacity-50"
              title="Refresh Speaking Voices and Playbacks"
              data-testid="refresh-speaking-voices-btn"
            >
              <RefreshCw className={`w-3 h-3 ${isRefreshingVoiceData || voiceCatalogLoading ? 'animate-spin' : ''}`} />
              <span>{isRefreshingVoiceData || voiceCatalogLoading ? 'Refreshing…' : 'Refresh'}</span>
            </button>
            <span className="text-[11px] text-[#8C879A]">
              Click Play to listen · Click row to choose
            </span>
          </div>

          {/* Compact Category & Gender Filters */}
          <div className="flex items-center gap-1.5 text-xs">
            <div className="flex rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] p-0.5">
              {[
                { id: 'all', label: `All (${voiceCategoryCounts.all})`, testId: 'voice-filter-all' },
                { id: 'conversational', aliases: ['support', 'care'], label: `Conversational (${voiceCategoryCounts.conversational})`, testId: 'voice-filter-conversational' },
                { id: 'promotional', aliases: ['sales', 'operations'], label: `Commercial / Promotional (${voiceCategoryCounts.promotional})`, testId: 'voice-filter-promotional' },
              ].map((c) => {
                const isActive = activeCategory === c.id || (c.aliases && c.aliases.includes(activeCategory));
                return (
                  <button
                    key={c.id}
                    type="button"
                    data-testid={c.testId}
                    onClick={() => setActiveCategory(c.id)}
                    className={`px-2 py-0.5 text-[11px] font-medium rounded-md transition-all ${
                      isActive
                        ? 'bg-[#0F0E17] text-white shadow-2xs'
                        : 'text-[#524E5E] hover:text-[#0F0E17]'
                    }`}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>

            <div className="flex rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] p-0.5">
              {[
                { id: 'all', label: 'All' },
                { id: 'female', label: 'Female' },
                { id: 'male', label: 'Male' },
                { id: 'neutral', label: 'Neutral' },
              ].map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setGenderFilter(g.id)}
                  className={`px-2 py-0.5 text-[11px] font-medium rounded-md transition-all ${
                    genderFilter === g.id
                      ? 'bg-[#6344E7] text-white shadow-2xs'
                      : 'text-[#524E5E] hover:text-[#0F0E17]'
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Dense Voice List / Table */}
        <div className="divide-y divide-[#F0EEF6] border border-[#E4E2EB] rounded-lg overflow-hidden">
          {filteredVoices.map((voice) => {
            const isSelected = currentVoiceId === voice.id;
            const isPlayingThis = playingVoiceId === voice.id;

            return (
              <div
                key={voice.id}
                data-testid={`voice-card-${voice.id}`}
                onClick={() => handleSelectVoice(voice)}
                className={`group flex items-center justify-between gap-3 px-3 py-2.5 transition-colors cursor-pointer select-none ${
                  isSelected
                    ? 'bg-[#6344E7]/8 border-l-4 border-l-[#6344E7]'
                    : 'bg-white hover:bg-[#FAF9FD]'
                }`}
              >
                {/* Left: Play/Stop Button + Avatar + Name + Tone */}
                <div className="flex items-center gap-3 min-w-0">
                  {/* Play Sample Button */}
                  <button
                    type="button"
                    data-testid={`voice-play-btn-${voice.id}`}
                    aria-label={`Play sample for ${voice.name}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePlayVoiceSample(voice);
                    }}
                    className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-transform active:scale-95 ${
                      isPlayingThis
                        ? 'bg-rose-600 text-white shadow-xs'
                        : 'bg-[#6344E7]/10 text-[#6344E7] hover:bg-[#6344E7] hover:text-white'
                    }`}
                  >
                    {isPlayingThis ? (
                      <Square className="w-3.5 h-3.5 fill-current" />
                    ) : (
                      <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                    )}
                  </button>

                  {/* Equalizer animation when playing */}
                  {isPlayingThis && (
                    <div className="flex items-center gap-0.5 h-3.5 shrink-0">
                      <span className="w-0.5 h-3 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-0.5 h-2 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-0.5 h-3.5 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}

                  {/* Name & Tone */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-bold text-[#0F0E17]">
                        {voice.name}
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-[#F0EEF6] text-[#524E5E] capitalize">
                        {voice.gender}
                      </span>
                      {(voice.tag === 'Indian' || voice.accent?.includes('Indian') || voice.useCase?.includes('Indian') || voice.tone?.includes('Telugu') || voice.tone?.includes('Hindi')) && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-700 border border-emerald-500/20">
                          🇮🇳 Indian
                        </span>
                      )}
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-[#6344E7]/10 text-[#6344E7] border border-[#6344E7]/20">
                        {voice.category === 'support' || voice.category === 'care'
                          ? 'Customer Care'
                          : voice.category === 'sales' || voice.category === 'energetic'
                          ? 'Sales & Outreach'
                          : 'Operations & Tech'}
                      </span>
                      <span className="hidden sm:inline-block text-[11px] font-medium text-[#716C7F]">
                        · {voice.tone}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#716C7F] truncate max-w-xs md:max-w-md">
                      {voice.accent
                        ? `${voice.accent}${voice.languageCode ? ` · ${voice.languageCode}` : ''}`
                        : voice.useCase}
                    </p>
                  </div>
                </div>

                {/* Right: Duration + Selection Action */}
                <div className="flex items-center gap-3 shrink-0">
                  <span className="hidden sm:inline-block text-[11px] text-[#8C879A] font-mono">
                    {voice.duration}
                  </span>

                  <button
                    type="button"
                    data-testid={`voice-select-btn-${voice.id}`}
                    disabled={isSavingStackSelection || stackSelectionConflict}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectTierVoice({ tier: 'premium' }, voice);
                    }}
                    className={`flex items-center gap-1 px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                      isSelected
                        ? 'bg-[#6344E7] text-white shadow-xs'
                        : 'bg-[#FAF9FD] text-[#524E5E] hover:bg-[#6344E7]/10 hover:text-[#6344E7] border border-[#E4E2EB]'
                    }`}
                  >
                    {isSelected ? (
                      <>
                        <Check className="w-3.5 h-3.5 stroke-[3]" />
                        <span>Selected</span>
                      </>
                    ) : (
                      <span>Choose</span>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
        </>
      )}

      {/* 3. Acoustic Calibration & Speech Dynamics (Admin Only - Hidden for Tenants) */}
      {isAdmin && (
        <div
          className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-3"
          data-testid="acoustic-calibration-card"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#6344E7]" />
              <span className="text-xs font-bold text-[#0F0E17]">
                Acoustic Calibration &amp; Speech Dynamics
              </span>
            </div>

            <button
              type="button"
              onClick={() => setShowAcousticControls((v) => !v)}
              className="flex items-center gap-1 text-[11px] font-semibold text-[#6344E7] hover:underline"
            >
              <span>{showAcousticControls ? 'Hide Sliders' : 'Fine-Tune Speed & Pitch'}</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAcousticControls ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Speed Slider always available or expanded */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
            {/* Speaking Pace */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-[#0F0E17]">Speaking Pace (Speed)</span>
                <span className="font-mono font-bold text-[#6344E7] text-[11px]">
                  {Number(currentSpeed || 1.0).toFixed(2)}x
                </span>
              </div>
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.05"
                value={currentSpeed}
                data-testid="speed-slider"
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setFormData((prev) => ({
                    ...prev,
                    voice: {
                      ...prev.voice,
                      speed: val,
                    },
                  }));
                }}
                className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-pointer accent-[#6344E7]"
              />
              <div className="flex justify-between text-[10px] text-[#8C879A]">
                <span>0.5x (Slow)</span>
                <span className="font-semibold text-[#6344E7]">1.0x (Industry Standard)</span>
                <span>2.0x (Fast)</span>
              </div>
            </div>

            {/* Quick Presets */}
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-[#0F0E17] block">
                Pacing Presets
              </span>
              <div className="flex items-center gap-1.5">
                {[
                  { label: 'Standard (1.0x)', speed: 1.0 },
                  { label: 'Patient Support (0.9x)', speed: 0.9 },
                  { label: 'Dynamic Sales (1.1x)', speed: 1.1 },
                ].map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => {
                      setFormData((prev) => ({
                        ...prev,
                        voice: {
                          ...prev.voice,
                          speed: p.speed,
                        },
                      }));
                    }}
                    className={`px-2.5 py-1 rounded text-[11px] font-medium border transition-all ${
                      Math.abs(currentSpeed - p.speed) < 0.01
                        ? 'bg-[#6344E7] text-white border-[#6344E7]'
                        : 'bg-[#FAF9FD] text-[#524E5E] border-[#E4E2EB] hover:bg-white'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Detailed sliders if expanded */}
          {showAcousticControls && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-[#F0EEF6]">
              {/* Pitch Offset - Disabled because providers manage pitch natively */}
              <div className="space-y-1.5 opacity-80">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-[#0F0E17]">Pitch Offset</span>
                  <span className="font-mono text-[#8C879A] text-[11px]">
                    0.00 (Neutral)
                  </span>
                </div>
                <input
                  type="range"
                  min="-0.15"
                  max="0.15"
                  step="0.05"
                  value={0}
                  disabled
                  className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-not-allowed opacity-50"
                />
                <p className="text-[10px] text-[#716C7F] italic">
                  Managed natively by provider voice persona (Not supported by provider API).
                </p>
              </div>

              {/* Stability - Disabled because providers manage prosody natively */}
              <div className="space-y-1.5 opacity-80">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-[#0F0E17]">Tone Stability</span>
                  <span className="font-mono text-[#8C879A] text-[11px]">
                    0.75 (Balanced Natural)
                  </span>
                </div>
                <input
                  type="range"
                  min="0.3"
                  max="1.0"
                  step="0.05"
                  value={0.75}
                  disabled
                  className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-not-allowed opacity-50"
                />
                <p className="text-[10px] text-[#716C7F] italic">
                  Native acoustic model control (Not supported by provider API).
                </p>
              </div>
            </div>
          )}
        </div>
      )}


    </div>
  );
}
