export interface Weakness {
  theme: string;
  frequency: number;
  average_severity: number;
}

export interface Profile {
  username: string;
  summary: {
    games: number;
    wins: number;
    losses: number;
    draws: number;
    local_accuracy: number | null;
  };
  weaknesses: Weakness[];
}

export interface IngestJob {
  job_id: number;
  username: string;
  status: string;
  deduplicated?: boolean;
  games_fetched?: number;
  games_analyzed?: number;
  games_failed?: number;
  error?: string | null;
}

export interface StyleMatch {
  gm_name: string;
  similarity: number;
  source: string;
}

export interface StyleGap {
  username: string;
  gm_name: string;
  player: Record<string, number>;
  grandmaster: Record<string, number>;
  gap: Record<string, number>;
}

export interface OpeningStat {
  opening: string;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  local_accuracy: number | null;
}

export interface Blunder {
  id: number;
  game_id: number;
  ply: number;
  fen: string;
  played_move: string;
  best_move: string | null;
  centipawn_loss: number;
  theme: string;
}

export interface DrillCard {
  card_id: number;
  theme: string;
  box: number;
  due_at: string;
  fen: string;
  label: string;
  orientation: "white" | "black";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AuthSession {
  authenticated: boolean;
  auth_required: boolean;
  token?: string | null;
  expires_at?: string | null;
}
