import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, AudioLines, Check, ChevronDown, Globe2, Headphones, MessageSquare, PhoneOutgoing, Play, ShieldCheck, Square, Workflow } from 'lucide-react';
import { VOICE_SAMPLES, sampleDurationLabel } from '../services/marketingVoice';
import { voiceAgent } from '../services/voiceAgent';
import { usePricingCatalog } from '../lib/usePricingCatalog';
import { PricingCards } from './PricingCards';
import { UsageCalculator } from './UsageCalculator';
import '../styles/landing.css';

const WORKFLOWS = [
  { id: 'sales', title: 'Turn enquiries into opportunities', label: 'Sales & enquiries', icon: PhoneOutgoing,
    description: 'Give every interested caller a useful conversation. Answer the question, understand the requirement, and leave your team a clear next step.',
    steps: ['Answer from your approved business information', 'Capture requirements and buying intent', 'Review the lead and requested follow-up'], result: 'An enquiry your team can act on.', example: 'Real estate · Education · Professional services' },
  { id: 'support', title: 'Make the first conversation count', label: 'Customer support', icon: Headphones,
    description: 'Handle familiar questions without making callers work through a phone tree. Keep your answers, boundaries, and escalation guidance in one place.',
    steps: ['Understand the caller’s question', 'Explain the relevant service or policy', 'Capture unresolved requests for your team'], result: 'Helpful answers. Better context for your team.', example: 'Local businesses · Service teams · Customer care' },
  { id: 'campaigns', title: 'Give your outreach a clear purpose', label: 'Outbound campaigns', icon: Workflow,
    description: 'Move from a contact list to a focused calling campaign. Set the objective, choose your agent, and review what happened after each conversation.',
    steps: ['Select leads or upload a contact list', 'Review your agent, audience, and campaign settings', 'Track call outcomes and prioritise the next action'], result: 'A campaign you can inspect, call by call.', example: 'Lead qualification · Re-engagement · Follow-ups' },
];

const QUESTIONS = [
  ['Do I need to know how to code?', 'No. Describe your business, review the generated script, choose an available voice, and test your agent in the workspace. You control the objectives, objection guidance, and details it should collect.'],
  ['Can I use it for inbound and outbound calls?', 'Yes. Configure an agent for incoming enquiries or outgoing calls. For list-based outreach, create a campaign and review its audience and calling settings before starting. Phone availability depends on your workspace configuration.'],
  ['Which languages and voices can I choose?', 'The workspace shows the languages and voices available for your selected tier. Preview the voice and test your actual script before using it with customers.'],
  ['Can it book appointments or update my CRM?', 'Connected actions depend on the integrations you enable. Add a supported calendar or CRM for the workflow you need. Without that connection, the agent can capture an enquiry or a callback request rather than claim a booking is confirmed.'],
  ['What happens after the call?', 'Review the transcript, summary, captured details, and outcome in your workspace. Use the lead pipeline and callback list to organise follow-up, and mark converted leads when they become customers. Callback requests do not automatically schedule a redial.'],
  ['How does billing work?', 'Fund your wallet and choose an available voice tier. Your workspace shows the applicable calling rates, usage, and checkout taxes. Browser-agent and phone-call rates can differ, so review the rate for the channel you use.'],
];

function SectionIntro({ eyebrow, title, children }) {
  return <div className="landing-intro"><p className="landing-eyebrow">{eyebrow}</p><h2>{title}</h2>{children && <p className="landing-description">{children}</p>}</div>;
}

function VoicePreview({ onGetStarted }) {
  const [sampleId, setSampleId] = useState('real-estate');
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const audioRef = useRef(null);
  const attemptRef = useRef(0);
  const sample = VOICE_SAMPLES.find(item => item.id === sampleId) || VOICE_SAMPLES[0];

  const stop = () => {
    attemptRef.current += 1;
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setPlaying(false);
    setLoading(false);
  };
  useEffect(() => {
    const audio = audioRef.current;
    return () => { attemptRef.current += 1; audio?.pause(); };
  }, []);

  const toggle = async () => {
    if (playing || loading) { stop(); return; }
    setError('');
    setLoading(true);
    const attempt = ++attemptRef.current;
    voiceAgent.stopTTS();
    try {
      await audioRef.current.play();
      if (attempt === attemptRef.current) { setLoading(false); setPlaying(true); }
    } catch {
      if (attempt !== attemptRef.current) return;
      setPlaying(false);
      setLoading(false);
      setError('Audio could not start. Please try again.');
    }
  };

  return <section id="talk-to-ai" className="landing-section landing-demo" aria-labelledby="landing-demo-title">
    <div className="landing-container landing-split">
      <div>
        <p className="landing-eyebrow"><AudioLines size={17} aria-hidden="true" /> Hear the difference</p>
        <h2 id="landing-demo-title">Good conversations<br />start with listening.</h2>
        <p className="landing-description">Get a feel for the voice before you build. Listen to a short industry sample, then try an agent with your own business script.</p>
        <button className="landing-text-link" onClick={() => { stop(); onGetStarted(); }}>Make it your own <ArrowRight size={17} aria-hidden="true" /></button>
      </div>
      <div className="landing-player" data-testid="landing-voice-preview">
        <audio ref={audioRef} src={sample.url} preload="none" onEnded={stop} onPause={() => setPlaying(false)} onError={() => { setPlaying(false); setLoading(false); setError('Audio is unavailable. Choose another sample or try again.'); }} />
        <div className="landing-player-top"><span className="landing-player-icon"><AudioLines size={22} aria-hidden="true" /></span><span>Meet your next first impression.</span></div>
        <label htmlFor="landing-voice-sample">Choose a sample</label>
        <div className="landing-select-wrap"><select id="landing-voice-sample" value={sample.id} onChange={event => { stop(); setError(''); setSampleId(event.target.value); }}>{VOICE_SAMPLES.map(item => <option key={item.id} value={item.id}>{item.industry}</option>)}</select><ChevronDown size={18} aria-hidden="true" /></div>
        <blockquote key={sample.id}>“{sample.text}”</blockquote>
        <div className="landing-player-bottom">
          <button type="button" className="landing-play" onClick={toggle} aria-label={playing || loading ? 'Stop voice sample' : 'Play voice sample'}>{playing || loading ? <Square size={17} fill="currentColor" aria-hidden="true" /> : <Play size={19} fill="currentColor" aria-hidden="true" />}</button>
          <div><strong>{sample.label}</strong><span>Recorded voice sample · {sampleDurationLabel(sample.durationSeconds)}</span></div>
          <div className="landing-wave" aria-hidden="true">{[10, 18, 28, 16, 34, 23, 38, 20, 30, 14, 24, 10].map((height, i) => <i key={i} style={{ height }} />)}</div>
        </div>
        <p role="status" className="landing-audio-status">{error || (loading ? 'Loading sample…' : playing ? 'Playing sample' : 'Samples illustrate a voice and scenario. Your agent follows your own script and enabled actions.')}</p>
      </div>
    </div>
  </section>;
}

export function LandingSections({ onGetStarted, onSelectPlan, onNavigatePage }) {
  const [workflowId, setWorkflowId] = useState('sales');
  const workflow = WORKFLOWS.find(item => item.id === workflowId);
  const pricing = usePricingCatalog();

  return <div className="landing-refresh" data-testid="landing-refresh">
    <VoicePreview onGetStarted={onGetStarted} />

    <section id="capabilities" className="landing-section landing-product">
      <div className="landing-container">
        <div className="landing-section-header"><SectionIntro eyebrow="More than a conversation" title="Every call, a clearer next step.">Bring your agent, conversations, and leads into one workspace. See what was said and decide what happens next.</SectionIntro><a className="landing-text-link" href="#how-it-works">See how it works <ArrowDown size={17} aria-hidden="true" /></a></div>
        <figure className="landing-workspace"><div className="landing-workspace-label"><span>Inside your workspace</span><span>Example data</span></div><img src="/images/landing/workspace-preview.png" width="1320" height="850" loading="lazy" alt="Dialtact lead workspace showing pipeline stages, search and filters, agent ownership, and a sample qualified enquiry." /><figcaption>Your team’s next move, organised. Example workspace with fictional contact data.</figcaption></figure>
        <div className="landing-benefits">
          <div><MessageSquare size={22} aria-hidden="true" /><h3>Your knowledge. Your rules.</h3><p>Give your agent the facts, objectives, and objection guidance that fit your business.</p></div>
          <div><Globe2 size={22} aria-hidden="true" /><h3>A voice that fits your customers.</h3><p>Choose an available language and voice, then hear how your own script sounds.</p></div>
          <div><ShieldCheck size={22} aria-hidden="true" /><h3>Stay in control of the next step.</h3><p>Review outcomes, manage callback requests, and confirm when a lead converts.</p></div>
        </div>
      </div>
    </section>

    <section id="industries" className="landing-section landing-usecases">
      <div className="landing-container">
        <SectionIntro eyebrow="Built around your business" title="One platform. Different conversations.">Start with the work your team needs help with.</SectionIntro>
        <div className="landing-workflows">
          <div className="landing-workflow-options" role="group" aria-label="Explore calling workflows">
            {WORKFLOWS.map(item => { const Icon = item.icon; return <button key={item.id} aria-pressed={workflowId === item.id} aria-controls="landing-workflow-detail" onClick={() => setWorkflowId(item.id)}><Icon size={21} aria-hidden="true" /><span>{item.label}</span><ArrowRight size={18} aria-hidden="true" /></button>; })}
            <p>For real estate, education, local services, and the teams that keep customers moving.</p>
          </div>
          <div id="landing-workflow-detail" className="landing-workflow-detail" aria-live="polite" aria-atomic="true">
            <span className="landing-caption">{workflow.example}</span><h3>{workflow.title}</h3><p>{workflow.description}</p>
            <ol>{workflow.steps.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, '0')}</span>{step}</li>)}</ol>
            <div className="landing-workflow-result"><Check size={18} aria-hidden="true" /><strong>{workflow.result}</strong></div>
          </div>
        </div>
      </div>
    </section>

    <section id="how-it-works" className="landing-section landing-setup">
      <div className="landing-container">
        <SectionIntro eyebrow="A simple place to start" title="Your business brief. A working agent.">Build it, hear it, refine it. Bring your team in when you’re ready.</SectionIntro>
        <ol className="landing-steps">
          <li><span>01 / Define</span><h3>Tell us what the job is.</h3><p>Describe your business, the questions callers ask, and what a good conversation should achieve.</p></li>
          <li><span>02 / Make it yours</span><h3>Set the voice and boundaries.</h3><p>Review the script. Add objectives and objection guidance. Connect supported tools when your workflow needs them.</p></li>
          <li><span>03 / Put it to work</span><h3>Test before the first call.</h3><p>Try it in the browser, refine the conversation, then configure your phone workflow or campaign.</p></li>
        </ol>
        <div className="landing-integration-note"><div><Workflow size={22} aria-hidden="true" /><p><strong>Works with the connections you enable.</strong><span>Add supported calendars and CRM tools to take the next step during a call.</span></p></div><button className="landing-text-link" onClick={() => onNavigatePage('dashboard/integrations')}>Explore integrations <ArrowRight size={17} aria-hidden="true" /></button></div>
      </div>
    </section>

    <section id="pricing" className="landing-section landing-pricing">
      <div className="landing-container">
        <div className="landing-section-header">
          <SectionIntro eyebrow="Room to start. Room to grow." title="Choose the voice. See the cost.">These are the published rates right now. Fund your wallet, choose an available voice tier, and review the exact per-minute phone rate before calling.</SectionIntro>
          <a className="landing-text-link" href="#usage-calculator">Estimate your usage <ArrowDown size={17} aria-hidden="true" /></a>
        </div>
        <PricingCards
          catalog={pricing.data}
          loading={pricing.loading}
          error={pricing.error}
          onRetry={pricing.reload}
          onSelectPlan={onSelectPlan}
        />
        <p className="landing-caption landing-pricing-note">Rates are per minute. Each call locks its rate when it starts, and checkout confirms the applicable tax before payment. Available tiers depend on your workspace.</p>
      </div>
    </section>

    <section id="usage-calculator" className="landing-section landing-calculator">
      <div className="landing-container">
        <SectionIntro eyebrow="Plan before you dial" title="Estimate a month of phone calls.">Pick a voice tier, then set your volume by calls or by talk time. The estimate applies the same published per-minute rate shown above, and you can compare every published tier at that volume.</SectionIntro>
        <UsageCalculator
          catalog={pricing.data}
          loading={pricing.loading}
          error={pricing.error}
          onRetry={pricing.reload}
          onSelectPlan={onSelectPlan}
          syncUrl
        />
      </div>
    </section>

    <section id="faq" className="landing-section landing-faq">
      <div className="landing-container landing-faq-layout"><SectionIntro eyebrow="Before you get started" title="A few things you might be wondering." /><div>{QUESTIONS.map(([question, answer]) => <details key={question} name="landing-questions"><summary>{question}<ChevronDown size={19} aria-hidden="true" /></summary><p>{answer}</p></details>)}</div></div>
    </section>

    <section className="landing-section landing-final" aria-labelledby="landing-final-title"><div className="landing-container"><div className="landing-final-panel"><div><p className="landing-eyebrow">Make every conversation more useful</p><h2 id="landing-final-title">Give your next caller<br />a better first hello.</h2></div><div><button className="landing-button landing-button-light" onClick={onGetStarted}>Build your agent <ArrowRight size={18} aria-hidden="true" /></button><a href="#talk-to-ai">Or listen to a sample first <ArrowRight size={16} aria-hidden="true" /></a></div></div></div></section>
  </div>;
}
