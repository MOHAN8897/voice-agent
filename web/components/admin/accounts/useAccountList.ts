"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAdminResource } from "@/lib/useAdminResource";
import { ENDPOINTS, fetchMatchingIds, toQuery, type AccountsTab, type ListPage } from "./model";
import { useDebounced, type Selection } from "./ui";

export type Filters = Record<string, string>;

const DERIVED_KEYS = new Set(["minBalanceUsd", "maxBalanceUsd"]);

/**
 * Server-side list state for one Accounts tab: filters, sort, paging and the
 * selection. Any change to filters or sort clears the selection, so a bulk action
 * can never apply to rows the operator can no longer see.
 */
export function useAccountList<T>(
  tab: AccountsTab,
  initialFilters: Filters,
  defaultSort: string,
  scopeTenantId: string
) {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [sort, setSort] = useState(defaultSort);
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState<Selection>({ ids: new Set(), allMatching: false });

  const debouncedQ = useDebounced(filters.q ?? "", 300);
  const effective = useMemo(
    () => ({ ...filters, q: debouncedQ, tenantId: scopeTenantId || filters.tenantId || "", sort, dir }),
    [filters, debouncedQ, scopeTenantId, sort, dir]
  );
  const effectiveKey = JSON.stringify(effective);

  const lastKey = useRef(effectiveKey);
  useEffect(() => {
    if (lastKey.current === effectiveKey) return;
    lastKey.current = effectiveKey;
    setOffset(0);
    setSelection({ ids: new Set(), allMatching: false });
  }, [effectiveKey]);

  const url = `${ENDPOINTS[tab]}?${toQuery({ ...effective, limit, offset })}`;
  const list = useAdminResource<ListPage<T>>(url, [url]);

  const setFilter = useCallback((key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resetFilters = useCallback(() => setFilters({}), []);

  const toggleSort = useCallback(
    (key: string) => {
      if (sort === key) setDir((d) => (d === "asc" ? "desc" : "asc"));
      else {
        setSort(key);
        setDir(key === "name" || key === "email" || key === "e164" || key === "workspace" ? "asc" : "desc");
      }
    },
    [sort]
  );

  // Derived keys (balance band → min/max) are not separate filters for the operator.
  const activeFilterCount = Object.entries(filters).filter(([k, v]) => v && !DERIVED_KEYS.has(k)).length;
  const total = list.data?.total ?? 0;
  const selectedCount = selection.allMatching ? total : selection.ids.size;

  return {
    filters,
    setFilter,
    setFilters,
    resetFilters,
    activeFilterCount,
    effective,
    sort,
    dir,
    toggleSort,
    limit,
    setLimit: (n: number) => {
      setLimit(n);
      setOffset(0);
    },
    offset,
    setOffset,
    selection,
    setSelection,
    clearSelection: () => setSelection({ ids: new Set(), allMatching: false }),
    selectedCount,
    rows: list.data?.items ?? [],
    total,
    loading: list.loading,
    error: list.error,
    reload: list.reload,
    data: list.data,
  };
}

export type AccountList<T> = ReturnType<typeof useAccountList<T>>;

/**
 * Turn the current selection into concrete ids. For "all matching" the server is
 * asked again with the same filters; if the set changed since the operator typed
 * the confirmation, the action stops rather than touching rows they never saw.
 */
export async function resolveSelection(
  tab: AccountsTab,
  selection: Selection,
  effective: Record<string, string>,
  expectedCount: number
): Promise<string[]> {
  if (!selection.allMatching) return [...selection.ids];
  const res = await fetchMatchingIds(tab, effective);
  if (res.truncated) throw new Error(`More than ${res.ids.length} rows match. Narrow the filters and try again.`);
  if (res.ids.length !== expectedCount) {
    throw new Error(`The matching set changed (now ${res.ids.length}, was ${expectedCount}). Review the list and try again.`);
  }
  return res.ids;
}
