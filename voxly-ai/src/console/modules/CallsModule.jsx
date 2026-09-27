import React, { useEffect, useState } from 'react';
import {
  Search,
  Volume2,
  Sparkles,
  FileText,
  RefreshCw,
  Filter,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import { CALL_BUCKET_LABELS, callBucket, PHONE_STACK_LABEL } from '../../lib/phoneLabels';

export function CallsModule() {
  const {
    calls,
    selectedCallId,
    setSelectedCallId,
    agents,
    phoneNumbers,
    loadWorkspaceData,
  } = useWorkspace();
  const [filterDirection, setFilterDirection] = useState('All');
  const [filterAgentId, setFilterAgentId] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [agentId, setAgentId] = useState('');
  const [dialBusy, setDialBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [mainTab, setMainTab] = useState('history');
  const [historyBucket, setHistoryBucket] = useState('all');

  useEffect(() => {
    const stored =
      typeof window !== 'undefined' ? sessionStorage.getItem('voxly_calls_agent') : null;
    if (stored && agents.some((a) => a.id === stored)) {
      setAgentId(stored);
      setFilterAgentId(stored);
      sessionStorage.removeItem('voxly_calls_agent');
    }
  }, [agents]);

  const filteredCalls = calls.filter((call) => {
    const matchesAgent =
      filterAgentId === 'all' || call.agentId === filterAgentId || call.agentName === agents.find((a) => a.id === filterAgentId)?.name;
    const matchesDir = filterDirection === 'All' || call.direction.toLowerCase() === filterDirection.toLowerCase();
    const matchesSearch =
      (call.callerName || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (call.callerPhone || '').includes(searchQuery) ||
      (call.agentName || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (call.outcome || '').toLowerCase().includes(searchQuery.toLowerCase());
    return matchesDir && matchesSearch && matchesAgent;
  });

  const bucketFiltered = filteredCalls.filter((call) => {
    if (historyBucket === 'all') return true;
    const b = callBucket(call);
    if (historyBucket === 'answered') return b === 'answered' || b === 'inbound';
    return b === historyBucket;
  });

  const bucketCounts = filteredCalls.reduce(
    (acc, c) => {
      const b = callBucket(c);
      acc.all += 1;
      if (b === 'missed') acc.missed += 1;
      if (b === 'declined') acc.declined += 1;
      if (b === 'outbound') acc.outbound += 1;
      if (b === 'answered' || b === 'inbound') acc.answered += 1;
      return acc;
    },
    { all: 0, answered: 0, missed: 0, declined: 0, outbound: 0 }
  );

  const activeCall =
    bucketFiltered.find((c) => c.id === selectedCallId) ||
    (bucketFiltered.length > 0 ? bucketFiltered[0] : null);

  useEffect(() => {
    if (agents[0]?.id && !agentId) setAgentId(agents[0].id);
  }, [agents, agentId]);

  useEffect(() => {
    if (!activeCall?.id) {
      setTranscriptLines([]);
      return;
    }
    let cancelled = false;
    api.calls
      .transcript(activeCall.id)
      .then((data) => {
        if (!cancelled) setTranscriptLines(data.lines || []);
      })
      .catch(() => {
        if (!cancelled) setTranscriptLines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCall?.id]);

  const refreshCalls = async () => {
    setRefreshing(true);
    try {
      await loadWorkspaceData?.();
      showToast('Call list updated', 'success');
    } catch (e) {
      showToast(e.message || 'Could not refresh', 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const placeCall = async () => {
    if (!agentId || !toNumber.trim()) return;
    setDialBusy(true);
    try {
      await api.calls.triggerOutbound({
        agentId,
        toE164: toNumber.trim(),
        fromE164: fromNumber || null,
      });
      showToast('Outbound call started', 'success');
      await loadWorkspaceData?.();
    } catch (e) {
      showToast(e.message || 'Could not place call', 'error');
    } finally {
      setDialBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Calls ({calls.length})</h2>
          <p className="text-xs text-[#524E5E] mt-0.5 max-w-2xl">
            {PHONE_STACK_LABEL}: transcripts, recordings, and wallet usage for real phone conversations.
          </p>
        </div>
        <TactileButton variant="secondary" size="sm" icon={RefreshCw} loading={refreshing} onClick={refreshCalls}>
          Refresh
        </TactileButton>
      </div>

      <div className="flex items-center gap-1 p-1 rounded-2xl bg-white border border-[#E4E2EB] w-fit">
        {[
          { id: 'history', label: 'Call history' },
          { id: 'outbound', label: 'Place outgoing call' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setMainTab(t.id)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold ${
              mainTab === t.id ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E] hover:text-[#0F0E17]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {mainTab === 'outbound' && (
        <SolidCard className="p-4 space-y-3">
          <div>
            <div className="text-xs font-bold text-[#0F0E17]">Outgoing call</div>
            <p className="text-[11px] text-[#524E5E] mt-1">
              Needs wallet balance, a published agent script, and a phone line as caller ID. Rate limits apply.
            </p>
          </div>
          <div className="grid sm:grid-cols-4 gap-2">
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <select
              value={fromNumber}
              onChange={(e) => setFromNumber(e.target.value)}
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
            >
              <option value="">Agent phone line</option>
              {phoneNumbers.map((n) => (
                <option key={n.id} value={n.number}>
                  {n.label ? `${n.label} · ${n.number}` : n.number}
                </option>
              ))}
            </select>
            <input
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              placeholder="+91…"
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
            />
            <TactileButton variant="primary" size="sm" loading={dialBusy} onClick={placeCall}>
              Call now
            </TactileButton>
          </div>
        </SolidCard>
      )}

      {mainTab === 'history' && (
        <>
      <div className="flex flex-wrap items-center gap-1 p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
        {['all', 'answered', 'missed', 'declined', 'outbound'].map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setHistoryBucket(key)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold ${
              historyBucket === key ? 'bg-white text-[#0F0E17] shadow-xs' : 'text-[#524E5E]'
            }`}
          >
            {CALL_BUCKET_LABELS[key]} ({bucketCounts[key] ?? 0})
          </button>
        ))}
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
          {['All', 'Inbound', 'Outbound'].map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterDirection(tab)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                filterDirection === tab
                  ? 'bg-white text-[#0F0E17] shadow-xs'
                  : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <Filter className="w-3.5 h-3.5 text-[#8C879A]" />
          <select
            value={filterAgentId}
            onChange={(e) => setFilterAgentId(e.target.value)}
            className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2 py-1 text-xs"
          >
            <option value="all">All agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>
        </div>

        <div className="relative min-w-[240px]">
          <Search className="w-3.5 h-3.5 text-[#524E5E] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by caller, agent, outcome..."
            className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl pl-8 pr-3 py-1.5 text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
          />
        </div>
      </div>

      {/* Main Split View: Table on Left, Detail Drawer on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Calls Table (7 cols on large screens) */}
        <div className={`${activeCall ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
          <SolidCard padding="p-0" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                    <th className="py-3 px-4">Caller</th>
                    <th className="py-3 px-3">Agent</th>
                    <th className="py-3 px-3">Type</th>
                    <th className="py-3 px-3 font-mono">Duration</th>
                    <th className="py-3 px-3">Outcome</th>
                    <th className="py-3 px-4 text-right">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E4E2EB]">
                  {bucketFiltered.map((call) => {
                    const isSelected = activeCall && activeCall.id === call.id;
                    return (
                      <tr
                        key={call.id}
                        onClick={() => setSelectedCallId(call.id)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-[#6344E7]/10 font-medium' : 'hover:bg-[#FAF9FD]'
                        }`}
                      >
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-[#0F0E17]">{call.callerName}</div>
                          <div className="text-[10px] font-mono text-[#524E5E]">{call.callerPhone}</div>
                        </td>
                        <td className="py-3.5 px-3 text-[#524E5E] font-medium">{call.agentName}</td>
                        <td className="py-3.5 px-3">
                          <StatusBadge status={call.direction} size="xs" />
                        </td>
                        <td className="py-3.5 px-3 font-mono font-bold text-[#0F0E17]">{call.duration}</td>
                        <td className="py-3.5 px-3">
                          <span className="text-[11px] text-[#524E5E] truncate max-w-[150px] block">
                            {call.outcome}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right text-[11px] text-[#8C879A]">
                          {call.startedAt ? new Date(call.startedAt).toLocaleString() : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SolidCard>
        </div>

        {/* Call Detail Inspector Drawer (5 cols) */}
        {activeCall && (
          <div className="lg:col-span-5 space-y-4">
            <SolidCard className="space-y-4">
              {/* Drawer Header */}
              <div className="flex items-start justify-between pb-3 border-b border-[#E4E2EB]">
                <div>
                  <span className="text-[10px] font-mono text-[#8C879A] uppercase">
                    Call Record ID: {activeCall.id}
                  </span>
                  <h3 className="text-sm font-bold text-[#0F0E17] mt-0.5">
                    {activeCall.callerName} ({activeCall.callerPhone})
                  </h3>
                </div>
                <StatusBadge status={activeCall.channel || activeCall.direction} size="xs" />
              </div>

              {/* Dual-Track Audio Waveform Player Simulation */}
              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                <div className="flex items-center justify-between text-xs text-[#524E5E]">
                  <span className="flex items-center gap-1.5 font-semibold text-[#0F0E17]">
                    <Volume2 className="w-3.5 h-3.5 text-[#6344E7]" />
                    <span>Call Recording Audio</span>
                  </span>
                  <span className="font-mono text-[11px] text-[#524E5E]">
                    {activeCall.duration}
                  </span>
                </div>

                {/* Animated / Clickable Waveform Bars */}
                <div className="h-10 flex items-center gap-1 py-1">
                  {[20, 45, 60, 80, 50, 30, 75, 90, 100, 65, 40, 25, 60, 85, 40, 20, 70, 95, 80, 55, 35, 65, 90, 45, 30, 55, 75, 60, 40, 25].map(
                    (barHeight, idx) => (
                      <div
                        key={idx}
                        style={{ height: `${barHeight}%` }}
                        className={`flex-1 rounded-full ${idx < 8 ? 'bg-[#6344E7]' : 'bg-[#E4E2EB]'}`}
                      />
                    )
                  )}
                </div>

                <span className="text-[10px] font-mono text-[#524E5E]">
                    {activeCall.costInr != null
                      ? `₹${Number(activeCall.costInr).toFixed(2)}`
                      : activeCall.costUsd != null
                        ? `$${Number(activeCall.costUsd).toFixed(3)}`
                        : 'Usage billed at hangup'}
                    {activeCall.endReason ? ` · ${activeCall.endReason}` : ''}
                    {activeCall.pipeline ? ` · ${activeCall.pipeline}` : ''}
                </span>
              </div>

              {/* AI Structured Summary */}
              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17]">
                  <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
                  <span>AI Executive Summary</span>
                </div>
                <p className="text-xs text-[#524E5E] leading-relaxed">
                  {activeCall.summary}
                </p>

                {activeCall.extractedFields && (
                  <div className="pt-2 border-t border-[#E4E2EB] grid grid-cols-2 gap-2 text-[11px] font-mono">
                    {Object.entries(activeCall.extractedFields).map(([k, v]) => (
                      <div key={k} className="bg-white p-2 rounded-lg border border-[#E4E2EB] shadow-2xs">
                        <span className="text-[#8C879A] block text-[9px] uppercase tracking-wider">{k}</span>
                        <span className="text-[#0F0E17] truncate block font-semibold">{v}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Diarized Transcript Bubbles */}
              <div>
                <h4 className="text-xs font-bold text-[#0F0E17] mb-2.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#524E5E]" />
                  <span>Transcript ({transcriptLines.length} turns)</span>
                </h4>

                <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                  {transcriptLines.length === 0 && (
                    <p className="text-xs text-[#8C879A]">Transcript appears after the call finalizes.</p>
                  )}
                  {transcriptLines.map((t, idx) => {
                    const isAgent = (t.role || t.speaker) === 'assistant' || t.role === 'agent';
                    return (
                      <div
                        key={idx}
                        className={`p-3 rounded-xl text-xs leading-relaxed ${
                          isAgent
                            ? 'bg-white border border-[#E4E2EB] ml-3 shadow-2xs'
                            : 'bg-[#FAF9FD] border border-[#E4E2EB] mr-3'
                        }`}
                      >
                        <div className="flex items-center justify-between text-[10px] text-[#8C879A] mb-1 font-mono">
                          <span className={`font-bold ${isAgent ? 'text-[#6344E7]' : 'text-[#0F0E17]'}`}>
                            {isAgent ? activeCall.agentName : 'Caller'}
                          </span>
                        </div>
                        <p className="text-[#0F0E17]">{t.text}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </SolidCard>
          </div>
        )}
      </div>
        </>
      )}
    </div>
  );
}
