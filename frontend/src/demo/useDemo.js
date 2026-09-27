/**
 * The demo context and its hook.
 *
 * Separate from DemoProvider.jsx so that file exports only components,  * otherwise Vite's fast refresh cannot hot-reload the provider, which is
 * exactly the file worth iterating on while tuning a demo.
 */

import { createContext, useContext } from 'react';

export const DemoContext = createContext(null);

/**
 * Read demo state and controls from anywhere in the tree.
 *
 * Returns null outside a DemoProvider, so a component can call it
 * unconditionally without caring whether Demo Mode is mounted.
 */
export function useDemo() {
  return useContext(DemoContext);
}
