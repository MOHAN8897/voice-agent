import React, { useLayoutEffect, useRef, useState } from 'react';
import { Save } from 'lucide-react';
import { TactileButton } from '../../ui/TactileButton';

export function AgentSaveDock({ containerRef, scriptDirty, settingsDirty, saving, disabled, error, onSave, onDiscard }) {
  const [bounds, setBounds] = useState(null);
  const dockRef = useRef(null);
  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const measure = () => {
      const { left, width } = element.getBoundingClientRect();
      const dockWidth = Math.min(width, 800);
      setBounds({ left: left + (width - dockWidth) / 2, width: dockWidth });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    const dock = dockRef.current;
    const heightObserver = new ResizeObserver(() => {
      element.style.setProperty('--agent-save-dock-height', `${dock.getBoundingClientRect().height}px`);
    });
    heightObserver.observe(dock);
    window.addEventListener('resize', measure);
    measure();
    return () => {
      observer.disconnect(); heightObserver.disconnect(); window.removeEventListener('resize', measure);
      element.style.removeProperty('--agent-save-dock-height');
    };
  }, [containerRef]);

  return (
    <section ref={dockRef} aria-label="Unsaved agent changes" data-testid="agent-studio-unsaved"
      className="agent-save-dock" style={bounds || { visibility: 'hidden' }}>
      <div className="min-w-0" role="status" aria-live="polite">
        <p className="text-copy font-semibold text-ink">{saving ? 'Saving your changes…' : 'You have unsaved changes'}</p>
        <p className="mt-0.5 text-ui text-fg-body">
          {scriptDirty && settingsDirty ? 'Script & settings' : settingsDirty ? 'Agent settings' : 'Calling script'}
          {' · '}Save to apply to future calls.
        </p>
        {error && <p role="alert" className="mt-1 text-ui text-danger-fg">{error}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <TactileButton size="sm" variant="ghost" onClick={onDiscard} disabled={saving} data-testid="agent-studio-discard">Discard</TactileButton>
        <TactileButton size="sm" icon={Save} onClick={onSave} loading={saving} disabled={disabled}
          data-testid="agent-save" className="min-h-11 px-5">{saving ? 'Saving…' : 'Save changes'}</TactileButton>
      </div>
    </section>
  );
}
