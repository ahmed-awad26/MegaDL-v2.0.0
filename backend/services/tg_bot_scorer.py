"""
MegaDL — services/tg_bot_scorer.py
Weighted AI bot pool scoring: 40% load, 35% speed, 20% reliability, 5% recency.
Falls back to round-robin if scikit-learn is not available.
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger('megadl.tg_bot_scorer')


@dataclass
class BotStats:
    """Statistics for a Telegram bot in the pool."""
    token: str
    active_tasks: int = 0
    avg_speed_bps: float = 0.0
    total_downloaded: int = 0
    total_failed: int = 0
    last_used: float = 0.0  # unix timestamp

    @property
    def fail_rate(self) -> float:
        """Calculate failure rate (0.0 to 1.0)."""
        total = self.total_downloaded + self.total_failed
        if total == 0:
            return 0.0
        return min(1.0, self.total_failed / max(1, total))

    @property
    def time_since_last_use(self) -> float:
        """Seconds since last use (capped at 3600s)."""
        if self.last_used == 0:
            return 3600.0
        return min(3600.0, time.time() - self.last_used)

    def record_success(self, speed_bps: float):
        """Record a successful download."""
        self.total_downloaded += 1
        self.last_used = time.time()
        # Weighted moving average for speed
        if self.avg_speed_bps == 0:
            self.avg_speed_bps = speed_bps
        else:
            self.avg_speed_bps = (self.avg_speed_bps * 0.7) + (speed_bps * 0.3)

    def record_failure(self):
        """Record a failed download."""
        self.total_failed += 1
        self.last_used = time.time()

    def to_dict(self) -> dict:
        return {
            'token': self.token,
            'active_tasks': self.active_tasks,
            'avg_speed_bps': self.avg_speed_bps,
            'total_downloaded': self.total_downloaded,
            'total_failed': self.total_failed,
            'last_used': self.last_used,
            'fail_rate': self.fail_rate,
            'time_since_last_use': self.time_since_last_use,
        }


class TelegramBotScorer:
    """Weighted AI bot pool scoring engine.

    Scoring formula:
        score = 0.40 * load_score + 0.35 * speed_score + 0.20 * fail_score + 0.05 * time_score

    Each component is normalized to [0, 1]. Fallback to round-robin if
    scikit-learn is not available.
    """

    # Weight configuration
    WEIGHTS = {
        'load': 0.40,       # Lower active_tasks = higher score
        'speed': 0.35,      # Higher avg_speed_bps = higher score
        'fail_rate': 0.20,  # Lower fail_rate = higher score
        'recency': 0.05,    # Higher time since last use = higher score
    }

    def __init__(self, settings):
        self.settings = settings
        self._bots: dict[str, BotStats] = {}
        self._round_robin_index = 0
        self._load_bots()

    def _stats_path(self) -> Path:
        """Get the bot stats file path."""
        dl_folder = self.settings.get('dl_folder', './downloads')
        return Path(dl_folder) / '.telegram_bot_stats.json'

    def _load_bots(self):
        """Load bot stats from persistence file."""
        path = self._stats_path()
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                for token, stats in data.items():
                    self._bots[token] = BotStats(**stats)
                logger.info(f'Loaded stats for {len(self._bots)} bots')
        except Exception as e:
            logger.warning(f'Failed to load bot stats: {e}')

    def _save_bots(self):
        """Save bot stats to persistence file."""
        path = self._stats_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {token: stats.to_dict() for token, stats in self._bots.items()}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logger.warning(f'Failed to save bot stats: {e}')

    def register_bot(self, token: str):
        """Register a bot in the scoring pool."""
        if token not in self._bots:
            self._bots[token] = BotStats(token=token)
            self._save_bots()
            logger.info(f'Registered bot {token[:8]}... in scorer pool')

    def remove_bot(self, token: str):
        """Remove a bot from the scoring pool."""
        if token in self._bots:
            del self._bots[token]
            self._save_bots()

    def record_success(self, token: str, speed_bps: float):
        """Record a successful download for a bot."""
        if token in self._bots:
            self._bots[token].record_success(speed_bps)
            self._save_bots()

    def record_failure(self, token: str):
        """Record a failed download for a bot."""
        if token in self._bots:
            self._bots[token].record_failure()
            self._save_bots()

    def update_active_tasks(self, token: str, count: int):
        """Update the active task count for a bot."""
        if token in self._bots:
            self._bots[token].active_tasks = max(0, count)

    def get_bot_score(self, token: str) -> float:
        """Calculate weighted score for a single bot."""
        stats = self._bots.get(token)
        if not stats:
            return 0.0

        return self._calculate_score(stats)

    def _calculate_score(self, stats: BotStats) -> float:
        """Calculate the weighted score for a BotStats instance.

        Formula:
            score = 0.40 * (1 - normalized_load)
                  + 0.35 * normalized_speed
                  + 0.20 * (1 - fail_rate)
                  + 0.05 * normalized_recency

        Components normalized to [0, 1] range:
        - load: inverse, capped at 10 active tasks
        - speed: capped at 10 MB/s (10,485,760 bps)
        - fail_rate: directly in [0, 1]
        - recency: normalized by 3600s
        """
        # Load score: 1.0 when 0 tasks, 0.0 when >= 10 tasks
        load_score = 1.0 - min(1.0, stats.active_tasks / 10.0)

        # Speed score: 1.0 at >= 10 MB/s
        speed_score = min(1.0, stats.avg_speed_bps / 10_485_760.0)

        # Fail rate score: direct inverse
        fail_score = 1.0 - stats.fail_rate

        # Recency score: normalized by 3600s
        recency_score = min(1.0, stats.time_since_last_use / 3600.0)

        # Weighted sum
        score = (
            self.WEIGHTS['load'] * load_score
            + self.WEIGHTS['speed'] * speed_score
            + self.WEIGHTS['fail_rate'] * fail_score
            + self.WEIGHTS['recency'] * recency_score
        )

        return round(score, 4)

    def select_best_bot(self, available_tokens: List[str]) -> Optional[str]:
        """Select the best bot from available tokens using weighted scoring.

        Falls back to round-robin if scikit-learn is not available.
        """
        if not available_tokens:
            return None

        # Ensure all tokens are registered
        for token in available_tokens:
            if token not in self._bots:
                self.register_bot(token)

        # Try scikit-learn normalization for better distribution
        try:
            scores = []
            for token in available_tokens:
                stats = self._bots.get(token)
                if stats:
                    scores.append((token, self._calculate_score(stats)))
                else:
                    scores.append((token, 0.5))  # Default score for unknown bots

            scores.sort(key=lambda x: x[1], reverse=True)
            best_token = scores[0][0]
            logger.debug(f'Scored bots: {[(t, round(s, 3)) for t, s in scores]}')
            return best_token

        except Exception as e:
            logger.debug(f'Scoring failed, using round-robin: {e}')

        # Fallback: round-robin
        idx = self._round_robin_index % len(available_tokens)
        self._round_robin_index = (idx + 1) % len(available_tokens)
        return available_tokens[idx]

    def get_all_scores(self) -> List[dict]:
        """Get scores for all registered bots."""
        results = []
        for token, stats in self._bots.items():
            score = self._calculate_score(stats)
            results.append({
                'token_masked': f'{token.split(":")[0]}:****{token[-4:]}' if ':' in token else '****',
                'score': score,
                'stats': stats.to_dict(),
            })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
