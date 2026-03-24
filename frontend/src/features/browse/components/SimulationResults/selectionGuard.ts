let clearPendingInteractionBlock: (() => void) | null = null;

const SUPPRESSION_WINDOW_MS = 250;

export const suppressNextBrowseInteraction = (durationMs = SUPPRESSION_WINDOW_MS) => {
  if (typeof window === 'undefined' || clearPendingInteractionBlock) {
    return;
  }

  const clear = () => {
    window.removeEventListener('click', blockNextInteraction, true);
    window.clearTimeout(timeoutId);
    clearPendingInteractionBlock = null;
  };

  const blockNextInteraction = (event: Event) => {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    clear();
  };

  const timeoutId = window.setTimeout(clear, durationMs);
  clearPendingInteractionBlock = clear;

  window.addEventListener('click', blockNextInteraction, true);
};
