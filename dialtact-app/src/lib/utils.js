import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind class lists; used by the registry components (shadcn, Magic UI, React Bits). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
