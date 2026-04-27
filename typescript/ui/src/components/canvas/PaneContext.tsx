/**
 * PaneContext — provides the per-pane Zustand store to all child components.
 *
 * Usage:
 *   <PaneContext.Provider value={myPaneStore}>
 *     <BreadcrumbNav />
 *     <GraphCanvas />
 *   </PaneContext.Provider>
 *
 *   // In any child component:
 *   const nodes = usePaneStore(s => s.nodes);
 */
import { createContext, useContext } from 'react';
import { useStore } from 'zustand';
import type { PaneStore, PaneState } from '../../store/paneStore';

export const PaneContext = createContext<PaneStore | null>(null);

/** Read from the nearest pane's store. Throws if used outside a PaneContext. */
export function usePaneStore<T>(selector: (state: PaneState) => T): T {
  const store = useContext(PaneContext);
  if (!store) {
    throw new Error('usePaneStore must be used inside a <PaneContext.Provider>');
  }
  return useStore(store, selector);
}
