import { useEffect } from 'react';
import { isTourCompleted, setTourCompleted, startTourGuide } from '../services/tourGuide';

export { isTourCompleted, setTourCompleted, startTourGuide };

/**
 * Replaces the old centered modal dialog with Driver.js interactive component tour.
 * If rendered with isOpen={true}, launches the Driver.js component spotlight.
 */
export function GuidedTourModal({ isOpen, onClose, onLaunchWorkspace, user }) {
  useEffect(() => {
    if (isOpen) {
      startTourGuide(user, {
        force: true,
        onComplete: () => {
          onClose?.();
          onLaunchWorkspace?.();
        },
      });
    }
  }, [isOpen, user, onClose, onLaunchWorkspace]);

  return null;
}

export default GuidedTourModal;
