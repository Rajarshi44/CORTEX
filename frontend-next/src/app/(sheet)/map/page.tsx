"use client";

import { useMemo } from "react";
import ChoroplethMap, { type RegionStat } from "@/components/map/ChoroplethMap";
import { useGeo, useAlerts, useSummary } from "@/lib/queries";
import regionData from "@/data/india-regions.json";

/**
 * Aggregates the backend /api/geo payload (locations + events) and /api/alerts
 * into per-region crime intelligence stats that match the india-regions.json shapes.
 */
export default function MapLens() {
  const { data: geo } = useGeo();
  const { data: alertsData } = useAlerts();
  const { data: summaryData } = useSummary();

  const stats = useMemo(() => {
    const locations = geo?.locations ?? [];
    const events = geo?.events ?? [];
    const alerts = Array.isArray(alertsData) ? alertsData : [];

    // Build a lookup: region name (lowercase) → aggregated stat
    const regionMap = new Map<string, {
      entities: number; poi: number; events: number; alerts: number;
      threat: number; communities: Set<number>; documents: Set<string>;
      persons: number; phones: number; orgs: number; accounts: number;
      recentEvents: { kind: string; summary: string; at: string }[];
      threatSum: number; threatCount: number;
    }>();

    // Initialize every region from the JSON
    for (const d of regionData.districts) {
      regionMap.set(d.name.toLowerCase(), {
        entities: 0, poi: 0, events: 0, alerts: 0,
        threat: 0, communities: new Set(), documents: new Set(),
        persons: 0, phones: 0, orgs: 0, accounts: 0,
        recentEvents: [], threatSum: 0, threatCount: 0,
      });
    }

    // Helper: find the closest matching region for a location label
    const regionNames = regionData.districts.map((d) => d.name.toLowerCase());
    function matchRegion(label: string): string | null {
      const low = label.toLowerCase().trim();
      // Direct match
      if (regionMap.has(low)) return low;
      // Check if the label contains a known region name
      for (const name of regionNames) {
        if (low.includes(name) || name.includes(low)) return name;
      }
      // State abbreviation or partial
      return null;
    }

    // Aggregate locations
    for (const loc of locations) {
      const region = matchRegion(loc.label);
      if (!region) continue;
      const r = regionMap.get(region)!;
      r.entities += 1 + loc.actors;
      r.poi += loc.poi.length;
      r.persons += loc.actors;
      r.threatSum += loc.risk;
      r.threatCount += 1;
      for (const p of loc.poi) {
        r.documents.add(p.id);
      }
    }

    // Aggregate events
    for (const ev of events) {
      // Try to match by placed_at or summary
      const region = matchRegion(ev.placed_at ?? "") || matchRegion(ev.summary);
      if (!region) continue;
      const r = regionMap.get(region)!;
      r.events += 1;
      r.documents.add(ev.document_id);
      r.recentEvents.push({ kind: ev.kind, summary: ev.summary, at: ev.at });
      for (const eid of ev.entity_ids) {
        // Count entity types by heuristic on entity_id prefix if available
        // This is approximate — backend IDs don't carry type, so just count as entity
      }
    }

    // Aggregate alerts by matching entity names to regions (best-effort)
    for (const alert of alerts) {
      if (alert.description) {
        const region = matchRegion(alert.description);
        if (region) {
          regionMap.get(region)!.alerts += 1;
        }
      }
    }

    // Build final stats array
    const byRegion: RegionStat[] = regionData.districts.map((d) => {
      const r = regionMap.get(d.name.toLowerCase())!;
      const threat = r.threatCount > 0 ? r.threatSum / r.threatCount : 0;
      // Sort recent events by date descending
      r.recentEvents.sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""));

      return {
        name: d.name,
        entities: r.entities,
        poi: r.poi,
        events: r.events,
        alerts: r.alerts,
        threat: Math.min(1, threat),
        communities: r.communities.size,
        documents: r.documents.size,
        breakdown: {
          persons: r.persons,
          phones: r.phones,
          orgs: r.orgs,
          accounts: r.accounts,
        },
        recentEvents: r.recentEvents.slice(0, 5),
      };
    });

    return { byRegion };
  }, [geo, alertsData]);

  return <ChoroplethMap stats={stats} title="Threat Intelligence Heatmap" />;
}
