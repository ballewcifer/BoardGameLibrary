export interface Game {
  bgg_id: number;
  name: string;
  year?: number;
  image_url?: string;
  thumbnail_url?: string;
  image_path?: string;
  min_players?: number;
  max_players?: number;
  playing_time?: number;
  min_age?: number;
  weight?: number;
  avg_rating?: number;
  my_rating?: number;
  description?: string;
  categories?: string;
  mechanics?: string;
  designers?: string;
  publishers?: string;
  best_players?: string;
  my_comment?: string;
  own: number;
  last_synced?: string;
  is_favorite: number;
  has_insert: number;
  is_expansion: number;
  tags?: string;
}

export interface User {
  id: number;
  first_name: string;
  last_name: string;
  created_at: string;
}

export interface Loan {
  id: number;
  game_id: number;
  user_id: number;
  checked_out_at: string;
  returned_at?: string;
  due_date?: string;
  notes?: string;
  game_name?: string;
  first_name?: string;
  last_name?: string;
}

export interface Play {
  id: number;
  game_id: number;
  played_at: string;
  player_names?: string;
  winner?: string;
  notes?: string;
  duration_minutes?: number;
  scores?: string;
  game_name?: string;
}

export interface Stats {
  total_games: number;
  total_plays: number;
  total_members: number;
  checked_out: number;
}
