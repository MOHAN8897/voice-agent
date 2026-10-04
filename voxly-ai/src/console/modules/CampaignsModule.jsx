import React, { useState, useEffect, useRef } from 'react';
import {
  Megaphone,
  Plus,
  Play,
  Pause,
  FileSpreadsheet,
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  HelpCircle,
  Info,
  Download,
  Trash2,
  ArrowRight,
  ArrowLeft,
  Check,
  Eye,
  Sliders,
  Users,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { CampaignComplianceModal } from '../ui/CampaignComplianceModal';
import { CampaignCardSkeleton } from '../ui/Skeleton';
import { DncRegistryPanel } from './DncRegistryPanel';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';

const COUNTRY_OPTIONS = [
  { code: 'US', name: 'United States (+1)' },
  { code: 'IN', name: 'India (+91)' },
  { code: 'GB', name: 'United Kingdom (+44)' },
  { code: 'CA', name: 'Canada (+1)' },
  { code: 'AU', name: 'Australia (+61)' },
  { code: 'SG', name: 'Singapore (+65)' },
  { code: 'AE', name: 'United Arab Emirates (+971)' },
  { code: 'DE', name: 'Germany (+49)' },
  { code: 'FR', name: 'France (+33)' },
  { code: 'ZA', name: 'South Africa (+27)' },
  { code: 'PH', name: 'Philippines (+63)' },
  { code: 'NZ', name: 'New Zealand (+64)' },
];

const CANONICAL_FIELD_OPTIONS = [
  { value: 'phone', label: 'Phone Number (Required)', category: 'required' },
  { value: 'full_name', label: 'Full Name', category: 'recommended' },
  { value: 'first_name', label: 'First Name', category: 'recommended' },
  { value: 'last_name', label: 'Last Name', category: 'recommended' },
  { value: 'email', label: 'Email', category: 'recommended' },
  { value: 'company', label: 'Company', category: 'recommended' },
  { value: 'job_title', label: 'Job Title', category: 'recommended' },
  { value: 'country', label: 'Country', category: 'recommended' },
  { value: 'state', label: 'State / Province', category: 'recommended' },
  { value: 'city', label: 'City', category: 'recommended' },
  { value: 'timezone', label: 'Timezone', category: 'recommended' },
  { value: 'notes', label: 'Notes / Remarks', category: 'recommended' },
  { value: 'address', label: 'Address', category: 'optional' },
  { value: 'website', label: 'Website', category: 'optional' },
  { value: 'customer_id', label: 'Customer ID', category: 'optional' },
  { value: 'lead_id', label: 'Lead ID', category: 'optional' },
  { value: 'language', label: 'Language', category: 'optional' },
  { value: 'industry', label: 'Industry', category: 'optional' },
  { value: 'source', label: 'Source', category: 'optional' },
  { value: 'tags', label: 'Tags', category: 'optional' },
  { value: 'custom_field', label: 'Custom Field', category: 'custom' },
  { value: 'ignore', label: 'Ignore (Do not import)', category: 'ignore' },
];

export function CampaignsModule() {
  const {
    campaigns,
    createCampaign,
    toggleCampaignStatus,
    startCampaign,
    fetchCampaignAnalytics,
    agents,
    phoneNumbers,
    setPreferredOutboundFrom,
    outboundFromE164,
    isLoading,
  } = useWorkspace();

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [launchError, setLaunchError] = useState(null);
  const [analytics, setAnalytics] = useState({});
  const [activeMainTab, setActiveMainTab] = useState('campaigns'); // 'campaigns' | 'dnd'
  const [isComplianceOpen, setIsComplianceOpen] = useState(false);

  // 6-step Wizard State
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [importProgress, setImportProgress] = useState(0);

  // Step 1: Config
  const [config, setConfig] = useState({
    name: '',
    description: '',
    agentId: agents[0]?.id || '',
    fromE164: outboundFromE164 || '',
    defaultCountry: 'US',
  });

  // Step 2: Source selection
  const [contactSource, setContactSource] = useState('upload'); // 'upload' | 'paste' | 'list'
  const [uploadedFile, setUploadedFile] = useState(null);
  const [pastedText, setPastedText] = useState('');
  const [savedLists, setSavedLists] = useState([]);
  const [selectedListId, setSelectedListId] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  // Step 3: Parsed Data & Mapping
  const [parsedData, setParsedData] = useState(null); // { fileName, totalRows, headers, previewRows, detectedMappings, recognizedTemplate, warnings }
  const [columnMappings, setColumnMappings] = useState({}); // { [header]: canonicalKey }
  const [customFieldNames, setCustomFieldNames] = useState({}); // { [header]: customFieldName }
  const [saveTemplate, setSaveTemplate] = useState(false);
  const [templateName, setTemplateName] = useState('');

  // Step 4: Normalization & Validation
  const [duplicateStrategy, setDuplicateStrategy] = useState('keep_first');
  const [validationResult, setValidationResult] = useState(null); // { totalRows, validCount, invalidCount, duplicateCount, validContacts, invalidContacts, duplicateGroups }
  const [validationTab, setValidationTab] = useState('valid'); // 'valid' | 'invalid' | 'duplicates'

  // Step 5: Pacing & Compliance
  const [pacing, setPacing] = useState({
    concurrencyLimit: 10,
    callingHours: '09:00 - 18:00 (Local Recipient Time)',
    maxAttemptsPerContact: 2,
    retryDelayMinutes: 30,
  });

  // Step 6: Review & Variables
  const [variableCheck, setVariableCheck] = useState(null); // { ok, agentId, referencedVariables, missingCount, missingVariables, contactsWithMissingCount }
  const [variableAction, setVariableAction] = useState('proceed'); // 'proceed' | 'use_full_name' | 'skip'
  const [saveAsList, setSaveAsList] = useState(false);
  const [newListName, setNewListName] = useState('');

  useEffect(() => {
    if (!config.agentId && agents[0]?.id) {
      setConfig((prev) => ({ ...prev, agentId: agents[0].id }));
    }
  }, [agents, config.agentId]);

  useEffect(() => {
    if (!campaigns.length) return;
    campaigns.forEach((c) => {
      fetchCampaignAnalytics(c.id)
        .then((a) => setAnalytics((prev) => ({ ...prev, [c.id]: a })))
        .catch(() => {});
    });
  }, [campaigns, fetchCampaignAnalytics]);

  // Load saved contact lists on modal open
  useEffect(() => {
    if (isCreateModalOpen) {
      api.contacts
        .getLists()
        .then((res) => {
          if (res?.lists) setSavedLists(res.lists);
        })
        .catch(() => {});
    }
  }, [isCreateModalOpen]);

  const resetWizard = () => {
    setStep(1);
    setBusy(false);
    setLaunchError(null);
    setImportProgress(0);
    setUploadedFile(null);
    setPastedText('');
    setParsedData(null);
    setColumnMappings({});
    setCustomFieldNames({});
    setValidationResult(null);
    setVariableCheck(null);
    setSaveTemplate(false);
    setTemplateName('');
    setSaveAsList(false);
    setNewListName('');
  };

  const handleDownloadSample = () => {
    const sample =
      'Customer Name,Contact Number,Email ID,Company Name,Appointment Date,Plan\n' +
      'John Smith,+14155551234,john@gmail.com,ABC Corp,2026-10-15,Premium Plan\n' +
      'Sarah Wilson,+14155556789,sarah@gmail.com,Global Tech,2026-10-16,Standard Plan\n' +
      'Michael Brown,+12125559876,michael@gmail.com,Brown LLC,2026-10-18,Enterprise\n' +
      'Rajesh Patel,+919876543210,rajesh@zenith.in,Zenith Labs,2026-10-20,Custom\n';
    const blob = new Blob([sample], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'voxly_contacts_sample.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Step 2 -> 3: Process uploaded file or pasted text
  const handleProcessSource = async () => {
    setBusy(true);
    setLaunchError(null);

    try {
      let parsePayload = {};

      if (contactSource === 'upload') {
        if (!uploadedFile) {
          throw new Error('Please select or drag a CSV or Excel file.');
        }
        // Read file as base64
        const base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(uploadedFile);
        });
        parsePayload = {
          fileName: uploadedFile.name,
          contentBase64: base64,
        };
      } else if (contactSource === 'paste') {
        if (!pastedText.trim()) {
          throw new Error('Please paste at least one contact line.');
        }
        parsePayload = {
          fileName: 'pasted_contacts.csv',
          rawText: pastedText,
        };
      } else if (contactSource === 'list') {
        if (!selectedListId) {
          throw new Error('Please select a contact list.');
        }
        const listData = await api.contacts.getListContacts(selectedListId);
        const contacts = listData.contacts || [];
        if (!contacts.length) {
          throw new Error('The selected list has no contacts.');
        }
        // Bypass mapping directly to validation
        setValidationResult({
          totalRows: contacts.length,
          validCount: contacts.length,
          invalidCount: 0,
          duplicateCount: 0,
          validContacts: contacts.map((c) => ({
            phone: c.phone,
            first_name: c.first_name,
            last_name: c.last_name,
            full_name: c.full_name,
            email: c.email,
            company: c.company,
            job_title: c.job_title,
            country: c.country,
            city: c.city,
            state: c.state,
            timezone: c.timezone,
            notes: c.notes,
            custom_fields: c.custom_fields || {},
            raw_data: c.raw_data || {},
          })),
          invalidContacts: [],
          duplicateGroups: [],
        });
        setStep(4);
        setBusy(false);
        return;
      }

      // Call parse API
      const parsed = await api.contacts.parse(parsePayload);
      setParsedData(parsed);

      // Pre-fill mappings from detected mappings
      const initialMap = {};
      const initialCustom = {};
      Object.entries(parsed.detectedMappings || {}).forEach(([header, d]) => {
        initialMap[header] = d.targetField;
        if (d.targetField.startsWith('custom_field:')) {
          initialCustom[header] = d.targetField.replace('custom_field:', '');
        }
      });
      setColumnMappings(initialMap);
      setCustomFieldNames(initialCustom);

      if (parsed.recognizedTemplate) {
        showToast(`Recognized template: "${parsed.recognizedTemplate.templateName}"`, 'success');
      }

      setStep(3);
    } catch (err) {
      setLaunchError(err.message || 'Failed to parse contacts');
    } finally {
      setBusy(false);
    }
  };

  // Step 3 -> 4: Validate Mappings & Normalize
  const handleValidateMappings = async () => {
    setBusy(true);
    setLaunchError(null);

    try {
      // Validate that at least one column is mapped to 'phone'
      const hasPhone = Object.values(columnMappings).some(
        (val) => val === 'phone' || val.toLowerCase() === 'phone'
      );
      if (!hasPhone) {
        throw new Error('Phone Number is required. Please map one column to Phone Number.');
      }

      // Compile final mapping object with custom field keys
      const finalMapping = {};
      Object.entries(columnMappings).forEach(([hdr, val]) => {
        if (val === 'custom_field') {
          const customKey = (customFieldNames[hdr] || hdr).trim().toLowerCase().replace(/\s+/g, '_');
          finalMapping[hdr] = `custom_field:${customKey}`;
        } else {
          finalMapping[hdr] = val;
        }
      });

      // Save template if requested
      if (saveTemplate && templateName.trim()) {
        try {
          await api.contacts.saveTemplate({
            templateName: templateName.trim(),
            sourceHeaders: parsedData.headers,
            mapping: finalMapping,
            defaultCountry: config.defaultCountry,
          });
          showToast(`Saved template "${templateName.trim()}"`, 'success');
        } catch (e) {
          console.warn('Template save failed:', e);
        }
      }

      // chisel: enter step 4 with validation skeleton immediately while normalizer runs
      setStep(4);
      setValidationResult(null);

      // Call normalizePreview
      const normRes = await api.contacts.normalizePreview({
        rows: parsedData.previewRows,
        mapping: finalMapping,
        defaultCountry: config.defaultCountry,
        duplicateStrategy,
        sourceFileName: parsedData.fileName,
      });

      setValidationResult(normRes);
    } catch (err) {
      setStep(3);
      setLaunchError(err.message || 'Validation failed');
    } finally {
      setBusy(false);
    }
  };

  // Step 4 -> 5: Advance from validation
  const handleProceedToPacing = () => {
    if (!validationResult?.validContacts?.length) {
      setLaunchError('No valid contacts to dial. Please review your mapping or invalid numbers.');
      return;
    }
    setLaunchError(null);
    setStep(5);
  };

  // Step 5 -> 6: Check agent variables & go to review
  const handleCheckVariablesAndReview = async () => {
    setBusy(true);
    setLaunchError(null);

    try {
      const contactsSample = validationResult.validContacts.slice(0, 50);
      const varRes = await api.campaigns.validateVariables(config.agentId, contactsSample);
      setVariableCheck(varRes);
      setStep(6);
    } catch (err) {
      setLaunchError(err.message || 'Could not validate agent variables');
    } finally {
      setBusy(false);
    }
  };

  // Step 6: Launch Campaign
  const handleLaunchCampaign = async () => {
    setBusy(true);
    setLaunchError(null);
    setImportProgress(25);

    try {
      const contactsToLaunch = validationResult.validContacts;

      // Handle variable fallbacks if user opted for full_name
      if (variableAction === 'use_full_name') {
        contactsToLaunch.forEach((c) => {
          if (!c.first_name && c.full_name) {
            c.first_name = c.full_name.split(' ')[0] || c.full_name;
          }
        });
      }

      setImportProgress(50);

      // Save as contact list if checked
      let createdListId = null;
      if (saveAsList && newListName.trim()) {
        try {
          const listRes = await api.contacts.createList({
            name: newListName.trim(),
            description: `Imported for campaign ${config.name || 'New Campaign'}`,
            contacts: contactsToLaunch,
          });
          createdListId = listRes?.list?.id;
        } catch (e) {
          console.warn('Could not save list:', e);
        }
      }

      setImportProgress(75);

      if (config.fromE164) {
        setPreferredOutboundFrom?.(config.fromE164);
      }

      // Create campaign with compliance attestation and DND scrub enabled
      const res = await createCampaign({
        name: config.name.trim() || 'Outbound Campaign',
        description: config.description.trim() || undefined,
        agentId: config.agentId,
        fromE164: config.fromE164 || undefined,
        defaultCountry: config.defaultCountry,
        concurrencyLimit: pacing.concurrencyLimit,
        maxAttemptsPerContact: pacing.maxAttemptsPerContact,
        retryDelayMinutes: pacing.retryDelayMinutes,
        callingHours: pacing.callingHours,
        contactListId: createdListId || undefined,
        contacts: contactsToLaunch,
        autoStart: true,
        consentConfirmed: true,
        consentVersion: '2026-10-v1',
        dndScrubEnabled: true,
      });

      const scrubCount = res?.dndExcludedCount ?? res?.campaign?.dndExcludedCount ?? 0;
      if (scrubCount > 0) {
        showToast(
          `${scrubCount} number${scrubCount === 1 ? '' : 's'} on your tenant Do Not Call list were excluded.`,
          'info'
        );
      }

      setImportProgress(100);
      showToast(
        `Campaign "${config.name || 'Outbound Campaign'}" launched with ${contactsToLaunch.length - scrubCount} active contacts!`,
        'success'
      );
      setIsComplianceOpen(false);
      setIsCreateModalOpen(false);
      resetWizard();
    } catch (err) {
      setLaunchError(err.message || 'Failed to launch campaign');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Main Sub-navigation Tabs */}
      <div className="flex border-b border-[#E4E2EB] gap-6 text-xs sm:text-sm font-semibold">
        <button
          type="button"
          onClick={() => setActiveMainTab('campaigns')}
          className={`pb-3 transition-colors border-b-2 flex items-center gap-2 ${
            activeMainTab === 'campaigns'
              ? 'border-[#FF5C35] text-[#FF5C35]'
              : 'border-transparent text-[#524E5E] hover:text-[#0F0E17]'
          }`}
          data-testid="campaigns-tab-button"
        >
          <Megaphone className="w-4 h-4" />
          Campaigns ({campaigns.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveMainTab('dnd')}
          className={`pb-3 transition-colors border-b-2 flex items-center gap-2 ${
            activeMainTab === 'dnd'
              ? 'border-[#FF5C35] text-[#FF5C35]'
              : 'border-transparent text-[#524E5E] hover:text-[#0F0E17]'
          }`}
          data-testid="dnd-registry-tab-button"
        >
          <ShieldAlert className="w-4 h-4" />
          Do Not Call (DND) Registry
        </button>
      </div>

      {activeMainTab === 'dnd' ? (
        <DncRegistryPanel />
      ) : (
        <>
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Bulk Outbound Campaigns ({campaigns.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5 max-w-2xl">
            Intelligent campaign engine with automatic column detection, variable injection, and E.164
            carrier compliance.
          </p>
        </div>

        <TactileButton
          onClick={() => {
            resetWizard();
            setIsCreateModalOpen(true);
          }}
          variant="primary"
          icon={Plus}
          size="md"
        >
          New Campaign
        </TactileButton>
      </div>

      {/* Campaigns List */}
      <div className="space-y-4">
        {isLoading && campaigns.length === 0 ? (
          <CampaignCardSkeleton count={3} />
        ) : campaigns.length === 0 ? (
          <SolidCard className="py-12 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7] mx-auto">
              <Megaphone className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F0E17]">No campaigns running</h3>
              <p className="text-xs text-[#524E5E] mt-1 max-w-md mx-auto">
                Upload your customer spreadsheet or paste numbers to launch high-conversion voice AI campaigns.
              </p>
            </div>
            <TactileButton
              onClick={() => {
                resetWizard();
                setIsCreateModalOpen(true);
              }}
              variant="primary"
              icon={Plus}
              size="sm"
            >
              Create First Campaign
            </TactileButton>
          </SolidCard>
        ) : (
          campaigns.map((camp) => {
            const stats = analytics[camp.id] || {};
            const total = stats.attempts ?? camp.totalContacts ?? 0;
            const connected = stats.connects ?? camp.connectedCalls ?? 0;
            const agent = agents.find((a) => a.id === camp.agentId);
            return (
              <SolidCard key={camp.id} className="space-y-4">
                {/* Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#E4E2EB]">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7] shadow-2xs">
                      <Megaphone className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-[#0F0E17]">{camp.name}</h3>
                        <StatusBadge status={camp.status} size="xs" />
                      </div>
                      <div className="text-xs text-[#524E5E] mt-0.5">
                        Agent: <span className="font-semibold text-[#0F0E17]">{agent?.name || camp.agentName || '—'}</span>
                        {camp.description && <span className="text-[#8C879A] ml-2">· {camp.description}</span>}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {camp.status === 'draft' && (
                      <TactileButton
                        size="sm"
                        variant="primary"
                        icon={Play}
                        onClick={async () => {
                          try {
                            await startCampaign(camp.id);
                            showToast('Campaign started', 'success');
                          } catch (e) {
                            showToast(e.message || 'Could not start campaign', 'error');
                          }
                        }}
                      >
                        Start dialer
                      </TactileButton>
                    )}
                    <TactileButton
                      size="sm"
                      variant={camp.status === 'running' ? 'secondary' : 'primary'}
                      icon={camp.status === 'running' ? Pause : Play}
                      onClick={() => toggleCampaignStatus(camp.id)}
                    >
                      {camp.status === 'running' ? 'Pause Campaign' : 'Resume Dialing'}
                    </TactileButton>
                  </div>
                </div>

                {/* Metrics Ribbon */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center font-mono">
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase block">Total Contacts</span>
                    <span className="text-sm font-bold text-[#0F0E17]">{Number(total).toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase block">Answer Rate</span>
                    <span className="text-sm font-bold text-[#047857]">
                      {total ? Math.round((connected / total) * 100) : 0}%
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase block">Connected Calls</span>
                    <span className="text-sm font-bold text-[#0F0E17]">{connected}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase block">Leads Generated</span>
                    <span className="text-sm font-bold text-[#6344E7]">{camp.leadsGenerated || 0}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase block">Cost Incurred</span>
                    <span className="text-sm font-bold text-[#0F0E17]">{camp.costIncurred || '$0.00'}</span>
                  </div>
                </div>

                {/* Progress Bar & Concurrency Gauge */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-[#524E5E]">
                    <span>Dialing progress ({connected} / {total})</span>
                    <span className="font-mono font-bold text-[#0F0E17]">
                      {total ? Math.round((connected / total) * 100) : 0}%
                    </span>
                  </div>
                  <div className="h-2 w-full bg-[#F0EEF6] rounded-full overflow-hidden border border-[#E4E2EB]">
                    <div
                      style={{ width: `${total ? Math.round((connected / total) * 100) : 0}%` }}
                      className="h-full bg-[#6344E7] rounded-full transition-all duration-300"
                    />
                  </div>
                  <div className="flex justify-between text-[11px] text-[#8C879A] font-mono pt-1">
                    <span>Concurrency: {camp.concurrencyLimit} simultaneous lines</span>
                    <span>{camp.callingHours}</span>
                  </div>
                </div>
              </SolidCard>
            );
          })
        )}
      </div>

      {/* 6-STEP BULK CAMPAIGN WIZARD MODAL */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Launch Outbound Dialing Campaign"
        subtitle="Automatic column mapping, phone normalization, and variable validation."
        maxWidth="max-w-4xl"
      >
        <div className="space-y-6 text-xs">
          {/* Step Progression Bar */}
          <div className="flex items-center justify-between pb-3 border-b border-[#E4E2EB] overflow-x-auto gap-2">
            {[
              { num: 1, label: 'Campaign' },
              { num: 2, label: 'Contacts' },
              { num: 3, label: 'Map Columns' },
              { num: 4, label: 'Validate' },
              { num: 5, label: 'Pacing' },
              { num: 6, label: 'Review' },
            ].map((s) => (
              <div key={s.num} className="flex items-center gap-2 whitespace-nowrap">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-[11px] transition-all ${
                    step === s.num
                      ? 'bg-[#6344E7] text-white shadow-xs'
                      : step > s.num
                        ? 'bg-[#047857] text-white'
                        : 'bg-[#F0EEF6] text-[#8C879A]'
                  }`}
                >
                  {step > s.num ? <Check className="w-3.5 h-3.5" /> : s.num}
                </div>
                <span
                  className={`text-xs font-semibold ${
                    step === s.num ? 'text-[#0F0E17]' : 'text-[#8C879A]'
                  }`}
                >
                  {s.label}
                </span>
                {s.num < 6 && <div className="w-4 h-0.5 bg-[#E4E2EB] hidden sm:block" />}
              </div>
            ))}
          </div>

          {/* Error Banner */}
          {launchError && (
            <div className="p-3 rounded-xl bg-[#FEF2F2] border border-[#FCA5A5] text-[#991B1B] flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{launchError}</span>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 1: CAMPAIGN CONFIGURATION */}
          {/* ========================================================================= */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">Campaign Name *</label>
                <input
                  type="text"
                  value={config.name}
                  onChange={(e) => setConfig({ ...config, name: e.target.value })}
                  placeholder="e.g. Q4 Dental Hygiene Recall"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block font-bold text-[#0F0E17] mb-1">AI Employee / Voice Agent *</label>
                  <select
                    value={config.agentId}
                    onChange={(e) => setConfig({ ...config, agentId: e.target.value })}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  >
                    {agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} — {a.role}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-bold text-[#0F0E17] mb-1">Outbound Caller ID</label>
                  <select
                    value={config.fromE164}
                    onChange={(e) => setConfig({ ...config, fromE164: e.target.value })}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs font-mono text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  >
                    <option value="">Agent Assigned DID (Recommended)</option>
                    {phoneNumbers.map((n) => (
                      <option key={n.id} value={n.number}>
                        {n.number} {n.friendlyName ? `(${n.friendlyName})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block font-bold text-[#0F0E17] mb-1">
                    Default Country / Calling Country *
                  </label>
                  <select
                    value={config.defaultCountry}
                    onChange={(e) => setConfig({ ...config, defaultCountry: e.target.value })}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  >
                    {COUNTRY_OPTIONS.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-[#524E5E] mt-1">
                    Used to normalize phone numbers that lack an international dialing code.
                  </p>
                </div>

                <div>
                  <label className="block font-bold text-[#0F0E17] mb-1">Campaign Description (Optional)</label>
                  <input
                    type="text"
                    value={config.description}
                    onChange={(e) => setConfig({ ...config, description: e.target.value })}
                    placeholder="Brief description of the call objective"
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-[#E4E2EB]">
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={() => {
                    if (!config.name.trim()) {
                      setLaunchError('Campaign name is required.');
                      return;
                    }
                    setLaunchError(null);
                    setStep(2);
                  }}
                  icon={ArrowRight}
                >
                  Continue to Contacts
                </TactileButton>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 2: CONTACTS SELECTION */}
          {/* ========================================================================= */}
          {step === 2 && (
            <div className="space-y-5">
              {/* Option Selector Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  {
                    id: 'upload',
                    title: 'Upload CSV / XLSX',
                    desc: 'Any spreadsheet format — Voxly automatically detects columns.',
                    icon: UploadCloud,
                  },
                  {
                    id: 'paste',
                    title: 'Paste Contacts',
                    desc: 'Paste phone numbers or customer rows directly.',
                    icon: FileSpreadsheet,
                  },
                  {
                    id: 'list',
                    title: 'Existing Contact List',
                    desc: 'Choose from pre-normalized saved lists.',
                    icon: Users,
                  },
                ].map((opt) => {
                  const Icon = opt.icon;
                  const active = contactSource === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setContactSource(opt.id)}
                      className={`p-4 rounded-xl border text-left transition-all ${
                        active
                          ? 'bg-[#FAF9FD] border-[#6344E7] ring-1 ring-[#6344E7]'
                          : 'bg-white border-[#E4E2EB] hover:border-[#8C879A]'
                      }`}
                    >
                      <Icon className={`w-5 h-5 mb-2 ${active ? 'text-[#6344E7]' : 'text-[#524E5E]'}`} />
                      <h4 className="font-bold text-xs text-[#0F0E17]">{opt.title}</h4>
                      <p className="text-[11px] text-[#524E5E] mt-1 leading-snug">{opt.desc}</p>
                    </button>
                  );
                })}
              </div>

              {/* Option A: Upload File */}
              {contactSource === 'upload' && (
                <div className="space-y-3">
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDragging(false);
                      if (e.dataTransfer.files?.[0]) {
                        setUploadedFile(e.dataTransfer.files[0]);
                      }
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-colors ${
                      isDragging
                        ? 'border-[#6344E7] bg-[#F0EEF6]/50'
                        : uploadedFile
                          ? 'border-[#047857] bg-[#ECFDF5]'
                          : 'border-[#E4E2EB] hover:border-[#6344E7] bg-[#FAF9FD]'
                    }`}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={(e) => {
                        if (e.target.files?.[0]) setUploadedFile(e.target.files[0]);
                      }}
                      accept=".csv, .xlsx, .xls"
                      className="hidden"
                    />
                    <UploadCloud className="w-8 h-8 text-[#6344E7] mx-auto mb-2" />
                    {uploadedFile ? (
                      <div>
                        <span className="font-bold text-sm text-[#0F0E17]">{uploadedFile.name}</span>
                        <p className="text-[11px] text-[#047857] mt-1 font-semibold">
                          File selected ({(uploadedFile.size / 1024).toFixed(1)} KB) — click to replace
                        </p>
                      </div>
                    ) : (
                      <div>
                        <span className="font-bold text-xs text-[#0F0E17]">
                          Drag & drop CSV or Excel file here
                        </span>
                        <p className="text-[11px] text-[#524E5E] mt-1">or Browse files (.csv, .xlsx, .xls)</p>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-[#524E5E] pt-1">
                    <span>Upload your contacts — Voxly will automatically detect and map your columns.</span>
                    <button
                      type="button"
                      onClick={handleDownloadSample}
                      className="text-[#6344E7] font-semibold hover:underline flex items-center gap-1"
                    >
                      <Download className="w-3.5 h-3.5" /> Download sample file
                    </button>
                  </div>
                </div>
              )}

              {/* Option B: Paste Contacts */}
              {contactSource === 'paste' && (
                <div className="space-y-2">
                  <label className="block font-bold text-[#0F0E17]">
                    Paste contacts (one contact per line)
                  </label>
                  <p className="text-[11px] text-[#524E5E]">
                    Supported formats: Phone number alone, or comma-separated columns (e.g.{' '}
                    <code>John Smith, +14155551234, john@gmail.com, ABC Corp</code>).
                  </p>
                  <textarea
                    rows={8}
                    value={pastedText}
                    onChange={(e) => setPastedText(e.target.value)}
                    placeholder={'Name, Phone, Email, Company\nJohn Smith, +14155551234, john@example.com, Acme Corp\nSarah Wilson, +14155556789, sarah@example.com, Zenith'}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs font-mono leading-relaxed"
                  />
                </div>
              )}

              {/* Option C: Existing List */}
              {contactSource === 'list' && (
                <div className="space-y-3">
                  <label className="block font-bold text-[#0F0E17]">Select Reusable Contact List</label>
                  {savedLists.length === 0 ? (
                    <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center text-[#524E5E]">
                      No saved contact lists found. Upload a CSV to create your first list.
                    </div>
                  ) : (
                    <select
                      value={selectedListId}
                      onChange={(e) => setSelectedListId(e.target.value)}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="">-- Choose a contact list --</option>
                      {savedLists.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name} ({l.contact_count} contacts)
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {/* chisel: file parsing shimmer progress card */}
              {busy && (
                <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2 animate-pulse" aria-busy="true">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-[#0F0E17]">
                      {uploadedFile ? `Parsing ${uploadedFile.name}…` : 'Analyzing contact rows…'}
                    </span>
                    <span className="text-[#6344E7] font-mono text-[11px]">Detecting columns</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-[#E4E2EB] overflow-hidden">
                    <div className="h-full bg-[#6344E7] w-2/3 animate-pulse rounded-full" />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back
                </button>
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={handleProcessSource}
                  disabled={busy}
                  icon={ArrowRight}
                >
                  {busy ? 'Processing...' : 'Continue to Column Mapping'}
                </TactileButton>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 3: COLUMN MAPPING */}
          {/* ========================================================================= */}
          {step === 3 && parsedData && (
            <div className="space-y-4">
              {/* File Info Bar */}
              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="font-bold text-[#0F0E17] text-xs">{parsedData.fileName}</span>
                  <div className="flex items-center gap-3 text-[11px] text-[#524E5E] mt-0.5">
                    <span>{parsedData.totalRows} rows detected</span>
                    <span>·</span>
                    <span>{parsedData.headers?.length} columns detected</span>
                  </div>
                </div>
                {parsedData.recognizedTemplate && (
                  <span className="text-xs font-semibold text-[#047857] bg-[#ECFDF5] px-2.5 py-1 rounded-lg border border-[#A7F3D0]">
                    ✓ Recognized &quot;{parsedData.recognizedTemplate.templateName}&quot; format
                  </span>
                )}
              </div>

              {/* Mapping Instructions */}
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#0F0E17]">
                  We matched your columns automatically. Verify or adjust mappings below:
                </span>
                <span className="text-[11px] text-[#524E5E]">* Phone Number is required</span>
              </div>

              {/* Mapping Table */}
              <div className="border border-[#E4E2EB] rounded-xl overflow-hidden max-h-80 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-[#FAF9FD] border-b border-[#E4E2EB] sticky top-0 z-10 text-[#524E5E] font-semibold text-[11px]">
                    <tr>
                      <th className="p-2.5">Your Column</th>
                      <th className="p-2.5">Sample Values</th>
                      <th className="p-2.5">Voxly Field</th>
                      <th className="p-2.5 text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E4E2EB]">
                    {parsedData.headers?.map((header) => {
                      const det = parsedData.detectedMappings?.[header] || {};
                      const currentVal = columnMappings[header] || 'ignore';
                      const confidence = det.confidence ?? 50;
                      const samples = det.sampleValues || [];

                      return (
                        <tr key={header} className="hover:bg-[#FAF9FD]/60">
                          <td className="p-2.5 font-semibold text-[#0F0E17] whitespace-nowrap">
                            {header}
                          </td>
                          <td className="p-2.5 max-w-xs">
                            <div className="flex flex-wrap gap-1">
                              {samples.slice(0, 3).map((val, idx) => (
                                <span
                                  key={idx}
                                  className="text-[10px] bg-[#F0EEF6] px-1.5 py-0.5 rounded text-[#524E5E] truncate max-w-[120px]"
                                  title={String(val)}
                                >
                                  {String(val)}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="p-2.5">
                            <div className="space-y-1">
                              <select
                                value={currentVal.startsWith('custom_field:') ? 'custom_field' : currentVal}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setColumnMappings({ ...columnMappings, [header]: val });
                                }}
                                className="bg-white border border-[#E4E2EB] rounded-lg p-1.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                              >
                                <optgroup label="Required">
                                  <option value="phone">Phone Number (Required)</option>
                                </optgroup>
                                <optgroup label="Recommended">
                                  <option value="full_name">Full Name</option>
                                  <option value="first_name">First Name</option>
                                  <option value="last_name">Last Name</option>
                                  <option value="email">Email</option>
                                  <option value="company">Company</option>
                                  <option value="job_title">Job Title</option>
                                  <option value="country">Country</option>
                                  <option value="state">State</option>
                                  <option value="city">City</option>
                                  <option value="timezone">Timezone</option>
                                  <option value="notes">Notes</option>
                                </optgroup>
                                <optgroup label="Optional">
                                  <option value="address">Address</option>
                                  <option value="website">Website</option>
                                  <option value="customer_id">Customer ID</option>
                                  <option value="lead_id">Lead ID</option>
                                  <option value="language">Language</option>
                                  <option value="industry">Industry</option>
                                  <option value="source">Source</option>
                                  <option value="tags">Tags</option>
                                </optgroup>
                                <optgroup label="Other">
                                  <option value="custom_field">Custom Field</option>
                                  <option value="ignore">Ignore (Do not import)</option>
                                </optgroup>
                              </select>

                              {currentVal === 'custom_field' && (
                                <input
                                  type="text"
                                  value={customFieldNames[header] || ''}
                                  onChange={(e) =>
                                    setCustomFieldNames({
                                      ...customFieldNames,
                                      [header]: e.target.value,
                                    })
                                  }
                                  placeholder="Variable name (e.g. product)"
                                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded p-1 text-[11px]"
                                />
                              )}
                            </div>
                          </td>
                          <td className="p-2.5 text-right whitespace-nowrap">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                confidence >= 90
                                  ? 'bg-[#ECFDF5] text-[#047857]'
                                  : confidence >= 70
                                    ? 'bg-[#FEF3C7] text-[#B45309]'
                                    : 'bg-[#F3F4F6] text-[#6B7280]'
                              }`}
                            >
                              {confidence >= 90 ? '✓ ' : ''}
                              {confidence}%
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Save Mapping Template Toggle */}
              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                <label className="flex items-center gap-2 cursor-pointer font-bold text-xs text-[#0F0E17]">
                  <input
                    type="checkbox"
                    checked={saveTemplate}
                    onChange={(e) => setSaveTemplate(e.target.checked)}
                    className="accent-[#6344E7] w-4 h-4 rounded"
                  />
                  <span>Save this mapping for future uploads?</span>
                </label>
                {saveTemplate && (
                  <div className="pt-1">
                    <input
                      type="text"
                      value={templateName}
                      onChange={(e) => setTemplateName(e.target.value)}
                      placeholder="Template name (e.g. Salesforce Contact Export)"
                      className="w-full sm:w-80 bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    />
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back
                </button>
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={handleValidateMappings}
                  disabled={busy}
                  icon={ArrowRight}
                >
                  {busy ? 'Validating...' : 'Continue to Validation'}
                </TactileButton>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 4: VALIDATION & DUPLICATE HANDLING */}
          {/* ========================================================================= */}
          {/* chisel: 6-row table skeleton while normalizePreview validates contacts */}
          {step === 4 && !validationResult && (
            <div className="space-y-4 animate-pulse" aria-busy="true" aria-label="Validating contacts">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1">
                    <div className="h-2.5 w-16 bg-[#E4E2EB] rounded" />
                    <div className="h-5 w-12 bg-[#E4E2EB] rounded" />
                  </div>
                ))}
              </div>
              <div className="p-4 rounded-xl bg-white border border-[#E4E2EB] space-y-3">
                <div className="h-4 w-48 bg-[#E4E2EB] rounded" />
                <div className="space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-[#FAF9FD]">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full bg-[#E4E2EB]" />
                        <div className="h-3 w-28 bg-[#E4E2EB] rounded font-mono" />
                      </div>
                      <div className="h-4 w-16 bg-[#E4E2EB] rounded-full" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 4 && validationResult && (
            <div className="space-y-4">
              {/* Quality Stat Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                  <span className="text-[10px] text-[#8C879A] uppercase font-bold block">Total Rows</span>
                  <span className="text-base font-bold text-[#0F0E17] font-mono">
                    {validationResult.totalRows}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#ECFDF5] border border-[#A7F3D0]">
                  <span className="text-[10px] text-[#047857] uppercase font-bold block">Valid Contacts</span>
                  <span className="text-base font-bold text-[#047857] font-mono">
                    ✓ {validationResult.validCount}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#FEF2F2] border border-[#FCA5A5]">
                  <span className="text-[10px] text-[#991B1B] uppercase font-bold block">Invalid Numbers</span>
                  <span className="text-base font-bold text-[#991B1B] font-mono">
                    ⚠ {validationResult.invalidCount}
                  </span>
                </div>
                <div className="p-3 rounded-xl bg-[#FFFBEB] border border-[#FDE68A]">
                  <span className="text-[10px] text-[#B45309] uppercase font-bold block">Duplicates</span>
                  <span className="text-base font-bold text-[#B45309] font-mono">
                    ⚠ {validationResult.duplicateCount}
                  </span>
                </div>
              </div>

              {/* Duplicate Strategy Controls */}
              {validationResult.duplicateCount > 0 && (
                <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h4 className="font-bold text-xs text-[#0F0E17]">Duplicate Handling Strategy</h4>
                    <p className="text-[11px] text-[#524E5E]">
                      Multiple rows share the same phone number. Choose how to handle duplicates:
                    </p>
                  </div>
                  <select
                    value={duplicateStrategy}
                    onChange={(e) => {
                      setDuplicateStrategy(e.target.value);
                      // Re-trigger validation with new strategy
                      handleValidateMappings();
                    }}
                    className="bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs font-semibold text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  >
                    <option value="keep_first">Keep First Contact (Default)</option>
                    <option value="keep_last">Keep Last Contact</option>
                    <option value="merge">Merge Custom Fields</option>
                    <option value="remove">Remove All Duplicates</option>
                  </select>
                </div>
              )}

              {/* View Selector Tabs */}
              <div className="flex items-center gap-2 border-b border-[#E4E2EB] pb-2">
                <button
                  type="button"
                  onClick={() => setValidationTab('valid')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                    validationTab === 'valid'
                      ? 'bg-[#0F0E17] text-white'
                      : 'text-[#524E5E] hover:bg-[#FAF9FD]'
                  }`}
                >
                  Valid Contacts ({validationResult.validCount})
                </button>
                {validationResult.invalidCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setValidationTab('invalid')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                      validationTab === 'invalid'
                        ? 'bg-[#B42318] text-white'
                        : 'text-[#B42318] hover:bg-[#FEF2F2]'
                    }`}
                  >
                    Invalid Rows ({validationResult.invalidCount})
                  </button>
                )}
                {validationResult.duplicateCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setValidationTab('duplicates')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                      validationTab === 'duplicates'
                        ? 'bg-[#B45309] text-white'
                        : 'text-[#B45309] hover:bg-[#FFFBEB]'
                    }`}
                  >
                    Duplicates ({validationResult.duplicateCount})
                  </button>
                )}
              </div>

              {/* Tab 1: Valid Contacts Preview */}
              {validationTab === 'valid' && (
                <div className="border border-[#E4E2EB] rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-[#FAF9FD] border-b border-[#E4E2EB] sticky top-0 z-10 text-[#524E5E] text-[11px]">
                      <tr>
                        <th className="p-2">Name</th>
                        <th className="p-2">Phone (E.164)</th>
                        <th className="p-2">Email</th>
                        <th className="p-2">Company</th>
                        <th className="p-2">Custom Fields</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E4E2EB]">
                      {validationResult.validContacts?.slice(0, 100).map((c, i) => (
                        <tr key={i} className="hover:bg-[#FAF9FD]/60">
                          <td className="p-2 font-semibold text-[#0F0E17]">
                            {c.full_name || `${c.first_name || ''} ${c.last_name || ''}`.trim() || '—'}
                          </td>
                          <td className="p-2 font-mono text-[#047857]">{c.phone}</td>
                          <td className="p-2 text-[#524E5E]">{c.email || '—'}</td>
                          <td className="p-2 text-[#524E5E]">{c.company || '—'}</td>
                          <td className="p-2 text-[10px] text-[#8C879A]">
                            {Object.entries(c.custom_fields || {}).map(([k, v]) => (
                              <span key={k} className="inline-block bg-[#F0EEF6] px-1.5 py-0.5 rounded mr-1">
                                {k}: {String(v)}
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tab 2: Invalid Rows */}
              {validationTab === 'invalid' && (
                <div className="border border-[#FCA5A5] rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-[#FEF2F2] border-b border-[#FCA5A5] sticky top-0 z-10 text-[#991B1B] text-[11px]">
                      <tr>
                        <th className="p-2">Row #</th>
                        <th className="p-2">Raw Value</th>
                        <th className="p-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#FEE2E2]">
                      {validationResult.invalidContacts?.map((inv, i) => (
                        <tr key={i}>
                          <td className="p-2 font-mono font-bold text-[#991B1B]">{inv.rowNumber}</td>
                          <td className="p-2 font-mono text-[#524E5E]">{inv.rawValue || '—'}</td>
                          <td className="p-2 text-[#991B1B]">{inv.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tab 3: Duplicates */}
              {validationTab === 'duplicates' && (
                <div className="border border-[#FDE68A] rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                  <div className="p-3 bg-[#FFFBEB] text-[#92400E] text-[11px] border-b border-[#FDE68A]">
                    Showing duplicate groups detected in file:
                  </div>
                  <div className="divide-y divide-[#FEF3C7] p-2 space-y-2">
                    {validationResult.duplicateGroups?.map((grp, i) => (
                      <div key={i} className="text-xs p-2">
                        <span className="font-mono font-bold text-[#B45309]">{grp.phone}</span>
                        <span className="text-[#8C879A] ml-2">({grp.rows?.length} occurrences)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back
                </button>
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={handleProceedToPacing}
                  icon={ArrowRight}
                >
                  Continue to Pacing & Compliance
                </TactileButton>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 5: PACING & COMPLIANCE */}
          {/* ========================================================================= */}
          {step === 5 && (
            <div className="space-y-4">
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="font-bold text-[#0F0E17]">
                    Max Concurrent Lines: {pacing.concurrencyLimit} simultaneous calls
                  </label>
                  <span className="font-mono text-[11px] text-[#6344E7] font-bold">
                    {pacing.concurrencyLimit} / 20 lines
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="20"
                  step="1"
                  value={pacing.concurrencyLimit}
                  onChange={(e) => setPacing({ ...pacing, concurrencyLimit: parseInt(e.target.value, 10) })}
                  className="w-full accent-[#6344E7]"
                />
                <span className="text-[10px] text-[#524E5E] mt-1 block">
                  Controls how many calls dial simultaneously. Paced to avoid carrier line congestion.
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <label className="font-bold text-[#0F0E17]">
                      Max Dial Attempts: {pacing.maxAttemptsPerContact}
                    </label>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    step="1"
                    value={pacing.maxAttemptsPerContact}
                    onChange={(e) =>
                      setPacing({ ...pacing, maxAttemptsPerContact: parseInt(e.target.value, 10) })
                    }
                    className="w-full accent-[#6344E7]"
                  />
                  <span className="text-[10px] text-[#524E5E] mt-1 block">
                    Retries if line is busy, unanswered, or fails.
                  </span>
                </div>

                <div>
                  <label className="block font-bold text-[#0F0E17] mb-1">
                    Retry Delay: {pacing.retryDelayMinutes} minutes
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="1440"
                    value={pacing.retryDelayMinutes}
                    onChange={(e) =>
                      setPacing({ ...pacing, retryDelayMinutes: parseInt(e.target.value, 10) || 30 })
                    }
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17]"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">Calling Hours Window</label>
                <input
                  type="text"
                  value={pacing.callingHours}
                  onChange={(e) => setPacing({ ...pacing, callingHours: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17]"
                />
                <span className="text-[10px] text-[#524E5E] mt-1 block">
                  Compliant calling hours prevent dialing recipients outside reasonable daytime hours.
                </span>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(4)}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back
                </button>
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={handleCheckVariablesAndReview}
                  disabled={busy}
                  icon={ArrowRight}
                >
                  {busy ? 'Validating Variables...' : 'Continue to Final Review'}
                </TactileButton>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STEP 6: FINAL REVIEW & VARIABLE VALIDATION */}
          {/* ========================================================================= */}
          {step === 6 && (
            <div className="space-y-4">
              {/* Campaign Summary Card */}
              <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                <div className="flex justify-between items-center pb-2 border-b border-[#E4E2EB]">
                  <span className="font-bold text-sm text-[#0F0E17]">{config.name || 'Outbound Campaign'}</span>
                  <span className="text-xs font-mono font-bold text-[#6344E7]">
                    {validationResult?.validCount} Contacts Ready
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] pt-1 font-mono">
                  <div>
                    <span className="text-[#8C879A] block">Agent:</span>
                    <span className="font-bold text-[#0F0E17]">
                      {agents.find((a) => a.id === config.agentId)?.name || 'Assigned Agent'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#8C879A] block">Caller ID:</span>
                    <span className="font-bold text-[#0F0E17]">{config.fromE164 || 'Agent DID'}</span>
                  </div>
                  <div>
                    <span className="text-[#8C879A] block">Default Country:</span>
                    <span className="font-bold text-[#0F0E17]">{config.defaultCountry}</span>
                  </div>
                  <div>
                    <span className="text-[#8C879A] block">Concurrency:</span>
                    <span className="font-bold text-[#0F0E17]">{pacing.concurrencyLimit} Lines</span>
                  </div>
                </div>
              </div>

              {/* Variable Validation Warning / Confirmation */}
              {variableCheck && (
                <div className="space-y-2">
                  {variableCheck.missingCount > 0 ? (
                    <div className="p-4 rounded-xl bg-[#FFFBEB] border border-[#FDE68A] space-y-3">
                      <div className="flex items-start gap-2 text-[#B45309]">
                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                        <div>
                          <h4 className="font-bold text-xs">Missing Script Variable Detected</h4>
                          <p className="text-[11px] mt-0.5">
                            Your agent script references{' '}
                            <code className="bg-[#FEF3C7] px-1 rounded font-bold">
                              {variableCheck.missingVariables?.map((v) => `{{${v}}}`).join(', ')}
                            </code>
                            , but{' '}
                            <span className="font-bold font-mono">
                              {variableCheck.contactsWithMissingCount}
                            </span>{' '}
                            contacts are missing this value.
                          </p>
                        </div>
                      </div>

                      <div className="pt-1 flex flex-wrap gap-2 text-xs">
                        <button
                          type="button"
                          onClick={() => setVariableAction('use_full_name')}
                          className={`px-3 py-1.5 rounded-lg border font-semibold transition-all ${
                            variableAction === 'use_full_name'
                              ? 'bg-[#B45309] text-white border-[#B45309]'
                              : 'bg-white text-[#B45309] border-[#FDE68A] hover:bg-[#FEF3C7]'
                          }`}
                        >
                          Use Full Name as fallback
                        </button>
                        <button
                          type="button"
                          onClick={() => setVariableAction('skip')}
                          className={`px-3 py-1.5 rounded-lg border font-semibold transition-all ${
                            variableAction === 'skip'
                              ? 'bg-[#B45309] text-white border-[#B45309]'
                              : 'bg-white text-[#B45309] border-[#FDE68A] hover:bg-[#FEF3C7]'
                          }`}
                        >
                          Skip variable / Leave blank
                        </button>
                        <button
                          type="button"
                          onClick={() => setStep(3)}
                          className="px-3 py-1.5 rounded-lg bg-white border border-[#E4E2EB] text-[#524E5E] font-semibold hover:bg-[#FAF9FD]"
                        >
                          Edit Mappings
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 rounded-xl bg-[#ECFDF5] border border-[#A7F3D0] flex items-center gap-2 text-[#047857]">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      <span className="text-xs font-semibold">
                        All script variables ({variableCheck.referencedVariables?.map((v) => `{{${v}}}`).join(', ') || 'none'}) are fully resolved!
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Save as Reusable Contact List */}
              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                <label className="flex items-center gap-2 cursor-pointer font-bold text-xs text-[#0F0E17]">
                  <input
                    type="checkbox"
                    checked={saveAsList}
                    onChange={(e) => setSaveAsList(e.target.checked)}
                    className="accent-[#6344E7] w-4 h-4 rounded"
                  />
                  <span>Save contacts as a reusable Contact List?</span>
                </label>
                {saveAsList && (
                  <input
                    type="text"
                    value={newListName}
                    onChange={(e) => setNewListName(e.target.value)}
                    placeholder="List name (e.g. October Recall Leads)"
                    className="w-full sm:w-80 bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                )}
              </div>

              {/* Progress Indicator when launching */}
              {busy && (
                <div className="space-y-1.5 p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                  <div className="flex justify-between text-xs text-[#0F0E17] font-semibold">
                    <span>Importing contacts & configuring live dialer...</span>
                    <span>{importProgress}%</span>
                  </div>
                  <div className="h-2 w-full bg-[#F0EEF6] rounded-full overflow-hidden">
                    <div
                      style={{ width: `${importProgress}%` }}
                      className="h-full bg-[#6344E7] rounded-full transition-all duration-300"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(5)}
                  disabled={busy}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Back
                </button>
                <TactileButton
                  variant="primary"
                  size="md"
                  onClick={() => setIsComplianceOpen(true)}
                  disabled={busy}
                  icon={Play}
                  data-testid="campaign-wizard-launch-btn"
                >
                  {busy ? 'Launching Campaign...' : 'Launch Campaign'}
                </TactileButton>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Compliance Attestation Modal */}
      <CampaignComplianceModal
        isOpen={isComplianceOpen}
        onClose={() => setIsComplianceOpen(false)}
        onConfirm={handleLaunchCampaign}
        campaignName={config.name || 'Outbound Campaign'}
        contactCount={validationResult?.validContacts?.length || 0}
        isSubmitting={busy}
      />
        </>
      )}
    </div>
  );
}
