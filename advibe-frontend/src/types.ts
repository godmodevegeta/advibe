export type TargetLocation = {
  location_query: string;
  neighborhood_hints: string[];
};
export type TribeScope = "overall" | "per_location";
export type Entity = {
  name: string;
  entity_id: string;
  subtype: string;
  affinity_hint?: number | null;
};
export type Tag = {
  name: string;
  tag_id: string;
  query?: string;
  affinity?: number | null;
  score?: number | null;
};
export type Signals = {
  locations?: TargetLocation[];
  tribe_scope?: TribeScope;
  brand_name: string | null;
  location_query: string | null;
  resolved_entities: { seed: Entity[]; competitors: Entity[] };
  resolved_tags: Tag[];
  insights_tags: string[];
  neighborhood_hints: string[];
  raw_signals: Record<string, unknown>;
};
export type AskState = {
  tribe_scope_explicit?: boolean;
  locations?: TargetLocation[];
  tribe_scope?: TribeScope;
  brand_name: string | null;
  product_description: string | null;
  location: string | null;
  location_query: string | null;
  resolved_entities: Signals["resolved_entities"];
  resolved_tags: Tag[];
  insights_tags: string[];
  explicit_seed_brands: string[];
  explicit_competitor_brands: string[];
  seed_tags: string[];
  neighborhood_hints: string[];
  suggested_seed_queries: string[];
  suggested_competitor_queries: string[];
  messages: string[];
};
export type AskResponse = {
  ready_for_session: boolean;
  missing_pillars: string[];
  assistant_message: string;
  crafted_prompt: string;
  suggestions: { seeds: Entity[]; competitors: Entity[]; locations: string[] };
  resolved_signals: Signals;
  state: AskState;
};
export type AskRequest = {
  selected_tribe_scope?: TribeScope;
  prompt: string | null;
  state: AskState | null;
  selected_seeds: Entity[];
  selected_competitors: Entity[];
  selected_location: string | null;
};
export type Preset = {
  id: string;
  title: string;
  description: string;
  prompt: string;
  location: string;
};
export type Pin = {
  latitude: number;
  longitude: number;
  affinity: number | null;
  neighborhood_label: string | null;
};
export type Place = {
  name: string;
  entity_id: string;
  latitude?: number | null;
  longitude?: number | null;
  distance_km?: number | null;
  affinity?: number | null;
};
export type Cohort = { cohort: string; label: string; lift: number };
export type Demographics = {
  scope?: string;
  aggregation_method?: string;
  targeting_method?: string;
  coverage?: {
    requested: number;
    returned: number;
    missing_seeds: { name: string; entity_id: string }[];
  };
  tag_blocks?: {
    entity_id: string;
    query: {
      age?: Record<string, number | null>;
      gender?: Record<string, number | null>;
    };
  }[];
  aggregate_age: Record<string, number | null>;
  aggregate_gender: Record<string, number | null>;
  all_seed_blocks: {
    name: string;
    age: Record<string, number | null>;
    gender: Record<string, number | null>;
  }[];
  top_positive_cohorts: Cohort[];
  excluded_cohorts: Cohort[];
};
export type Compare = {
  all_a_only_tags?: Tag[];
  all_b_only_tags?: Tag[];
  interpretation?: string;
  mixed_entity_types?: boolean;
  competitor_name: string;
  shared_tags: Tag[];
  a_only_tags: Tag[];
  b_only_tags: Tag[];
};
export type TrendRecord = {
  date: string;
  is_recent: boolean;
  population_rank: number | null;
  population_percentile: number | null;
  population_rank_velocity: number | null;
  velocity_fold_change: number | null;
  population_percent_delta: number | null;
};
export type TrendingResult = {
  status: "available" | "no_data" | "unsupported" | "error";
  reason: string;
  scope: "global";
  entity:
    | (Entity & {
        source: "selected_seed" | "related_reference";
        affinity?: number;
        source_seeds?: Entity[];
        discovery_location?: string;
      })
    | null;
  recent_window: { start_date: string; end_date: string };
  returned_date_range: { start_date: string; end_date: string } | null;
  records: TrendRecord[];
  recent_record_count: number;
  broader_window_used: boolean;
  attempts: unknown[];
  skipped_entities: unknown[];
};
export type Audience = {
  provenance?: {
    location_query: string;
    taste_scope: string;
    seed_entities: Entity[];
    verified_tags: Tag[];
    calls: unknown[];
  };
  demographics: Demographics;
  taste_vocabulary: Tag[];
  compare: Compare | null;
  trending:
    | TrendingResult
    | {
        status: string;
        entity?: string;
        window?: { start_date: string; end_date: string };
      }
    | null;
};
export type Packet = {
  packet_id: string;
  strategy_id: string;
  label: string;
  geo_pin: Pin | null;
  venues: Place[];
  artists: Place[];
  movies: Place[];
  podcasts: Place[];
  brands: Place[];
  taste_tags: Tag[];
  compare?: Compare | null;
};
export type Strategy = {
  location_query?: string;
  location_id?: string;
  packet?: Packet;
  location_variants?: Strategy[];
  id: string;
  tribe_name: string;
  strategic_angle: string;
  qloo_grounding_summary: string;
  cultural_system_prompt?: string;
  meta_adset_spec?: {
    name: string;
    status: string;
    age_min: number;
    age_max: number;
    genders: number[];
    geo_locations: {
      custom_locations: {
        latitude: number;
        longitude: number;
        radius: number;
        distance_unit: string;
      }[];
    };
  };
};
export type Output = {
  packets?: Packet[];
  audience_insights?: Audience;
  locations?: TargetLocation[];
  tribe_scope?: TribeScope;
  city_outputs?: Record<string, Output>;
  brand_name: string;
  location_query: string;
  demographics: Demographics;
  taste_vocabulary: Tag[];
  heatmap_pins: Pin[];
  strategies: Strategy[];
};
export type Artifacts = {
  trending?: TrendingResult;
  resolved_signals?: Signals;
  seed_signals?: Record<string, unknown>;
  campaign_brief?: Record<string, unknown>;
  geo_pins?: { heatmap_pins: Pin[]; places: Place[] };
  audience_insights?: Audience;
  packets?: Packet[];
  strategies?: Strategy[];
};
export type Patch = {
  [K in keyof Artifacts]-?: {
    type: "artifact_patch";
    artifact: K;
    data: NonNullable<Artifacts[K]>;
    timestamp: number;
  };
}[keyof Artifacts];
export type StreamEvent = (
  | Patch
  | {
      type: "phase_change";
      timestamp: number;
      phase: string;
      spinner_verb: string;
    }
  | {
      type: "qloo_call";
      timestamp: number;
      name: string;
      call_id?: string;
      entity?: { name: string; entity_id: string };
      window?: { start_date: string; end_date: string };
      window_kind?: "recent" | "history";
      http_status?: number | null;
      reason?: string;
      cached?: boolean;
      status: string;
      duration_ms?: number;
    }
  | {
      type: "checkpoint";
      timestamp: number;
      checkpoint_id: string;
      spinner_verb: string;
      data: Output;
    }
  | {
      type: "complete";
      timestamp: number;
      data: Output;
      duration_seconds: number;
    }
  | { type: "error"; timestamp: number; message: string; error_type: string }
) & { location_id?: string; location_query?: string };
