import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

/**
 * Resolves the user identifier (email or ID) from props or stored auth session.
 */
function getResolvedUserEmail(user) {
  if (user?.email) return user.email;
  try {
    const raw = localStorage.getItem('voxly_auth_session');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.email) return parsed.email;
    }
  } catch {}
  return user?.id || null;
}

/**
 * Checks whether the user has already completed or dismissed the guided tour.
 */
export function isTourCompleted(user) {
  try {
    const email = getResolvedUserEmail(user);
    if (email && localStorage.getItem(`voxly_tour_completed_${email}`) === 'true') {
      return true;
    }
    return localStorage.getItem('voxly_tour_completed_default') === 'true';
  } catch {
    return false;
  }
}

/**
 * Marks the guided tour as completed for the active user and session.
 */
export function setTourCompleted(user) {
  try {
    const email = getResolvedUserEmail(user);
    if (email) {
      localStorage.setItem(`voxly_tour_completed_${email}`, 'true');
    }
    localStorage.setItem('voxly_tour_completed_default', 'true');
  } catch {
    // ignore in sandboxed environments
  }
}

/**
 * Driver.js Interactive Component Spotlight Tour
 * Highlights 7 core components with page dimming and modern tactile popovers.
 */
export function startTourGuide(user, options = {}) {
  const { onComplete, force = false } = options;

  if (!force && isTourCompleted(user)) {
    return null;
  }

  // Ensure user is on overview dashboard so all target elements exist in DOM
  if (typeof window !== 'undefined' && !window.location.hash.startsWith('#dashboard/overview')) {
    window.location.hash = '#dashboard/overview';
  }

  let completedOrDestroyed = false;

  const markDone = () => {
    if (completedOrDestroyed) return;
    completedOrDestroyed = true;
    setTourCompleted(user);
    onComplete?.();
  };

  const steps = [
    {
      element: '[data-tour="create-agent"]',
      popover: {
        title: '🤖 Create Your Voice Agent',
        description:
          'Click here to build and deploy custom AI voice employees. Configure bespoke prompts, Telugu neural voices, and conversational workflows in seconds.',
        side: 'bottom',
        align: 'end',
      },
    },
    {
      element: '[data-tour="buy-number"]',
      popover: {
        title: '📞 Dedicated Phone Lines',
        description:
          'Provision regional Indian and toll-free virtual phone numbers for instant inbound call answering and automated high-volume outbound dialing.',
        side: 'bottom',
        align: 'end',
      },
    },
    {
      element: '[data-tour="nav-employees"]',
      popover: {
        title: '👥 AI Workforce Studio',
        description:
          'Manage your fleet of deployed agents, test conversational prompts live with our neural speech playground, and inspect performance metrics.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="nav-phone-numbers"]',
      popover: {
        title: '⚡ Telephony & Routing',
        description:
          'Connect phone numbers directly to designated agents, manage SIP credentials, recording disclosures, and automated fallback numbers.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="nav-campaigns"]',
      popover: {
        title: '📢 Campaigns & DND Scrubbing',
        description:
          'Execute high-scale outbound campaigns with mandatory compliance attestation and automated tenant-wide Do Not Call (DND) scrubbing.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="nav-calls"]',
      popover: {
        title: '📊 Live Transcripts & Sentiment',
        description:
          'Review dual-channel turn-by-turn conversational audio recordings, automated sentiment scoring, and auto-extracted qualification data.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="topbar-wallet"]',
      popover: {
        title: '💳 Balance & Minutes Wallet',
        description:
          'Monitor real-time per-second telephony usage and instantly top up your wallet with INR or USD credits with instant checkout.',
        side: 'bottom',
        align: 'end',
      },
    },
  ];

  const driverObj = driver({
    showProgress: true,
    animate: true,
    allowClose: true,
    overlayColor: '#0F0E17',
    overlayOpacity: 0.78,
    stagePadding: 6,
    stageRadius: 14,
    popoverClass: 'voxly-tour-popover',
    nextBtnText: 'Next Step →',
    prevBtnText: '← Back',
    doneBtnText: 'Launch Workspace',
    progressText: 'Step {{current}} of {{total}}',
    steps: steps,
    onPopoverRender: (popover) => {
      popover.wrapper.setAttribute('data-testid', 'guided-tour-popover');
      popover.title.setAttribute('data-testid', 'tour-step-title');
      popover.description.setAttribute('data-testid', 'tour-step-description');
      if (popover.nextButton) popover.nextButton.setAttribute('data-testid', 'tour-next-btn');
      if (popover.previousButton) popover.previousButton.setAttribute('data-testid', 'tour-prev-btn');
      if (popover.closeButton) popover.closeButton.setAttribute('data-testid', 'tour-close-btn');
      if (popover.progress) popover.progress.setAttribute('data-testid', 'tour-step-badge');
    },
    onCloseClick: () => {
      markDone();
      driverObj.destroy();
    },
    onDoneClick: () => {
      markDone();
      driverObj.destroy();
    },
    onDestroyStarted: () => {
      markDone();
      driverObj.destroy();
    },
    onDestroyed: () => {
      markDone();
    },
  });

  const launch = () => {
    try {
      driverObj.drive();
    } catch {
      // fallback safe ignore
    }
  };

  // Give React render loop time to mount the overview module and buttons
  if (typeof window !== 'undefined') {
    window.setTimeout(() => {
      const el =
        document.querySelector('[data-tour="create-agent"]') ||
        document.querySelector('[data-tour="nav-employees"]');
      if (el) {
        launch();
      } else {
        window.setTimeout(launch, 300);
      }
    }, 180);
  }

  return driverObj;
}
