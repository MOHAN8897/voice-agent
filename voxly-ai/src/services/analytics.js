/**
 * Lightweight, privacy-first telemetry and conversion dispatcher.
 * Adheres to GDPR/CCPA: no PII or raw audio metadata is stored.
 */

class AnalyticsService {
  constructor() {
    this.events = [];
    this.debug = process.env.NODE_ENV === 'development';
  }

  track(eventName, properties = {}) {
    const payload = {
      event: eventName,
      timestamp: new Date().toISOString(),
      properties: {
        ...properties,
        referrer: typeof document !== 'undefined' ? document.referrer : '',
        path: typeof window !== 'undefined' ? window.location.pathname : '/',
      },
    };

    this.events.push(payload);

    if (this.debug) {
      // In dev mode, console dispatch for verification
      // console.debug(`[Telemetry] ${eventName}`, payload.properties);
    }

    // Custom window event dispatch for external listeners (e.g. Segment, GTM)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('voxly_telemetry', { detail: payload })
      );
    }
  }

  // Pre-configured conversion shortcuts
  trackPageView(pageName) {
    this.track('page_view', { page: pageName });
  }

  trackCtaClick(location, label = 'Build Your Agent') {
    this.track('cta_build_agent_click', { location, label });
  }

  trackVoiceDemoStarted(triggerType = 'inline') {
    this.track('voice_demo_started', { trigger: triggerType });
  }

  trackPlanSelected(planName) {
    this.track('plan_selected', { plan: planName });
  }

  trackNewsletterSubscribed() {
    this.track('newsletter_subscribed');
  }
}

export const analytics = new AnalyticsService();
