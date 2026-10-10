"""Turn router & gatekeeper: selects LLM mode vs Scripted fallback."""
import os
import time
from collections import deque

LLM_HEALTH_TTL_SECONDS = 60
HARD_BUDGET_CAP_USD = 40.0

# In-memory tracking of health and spending
_last_failure_timestamp: float = 0.0
_estimated_spent_usd: float = 0.0


MAX_TURNS_PER_MINUTE = int(os.getenv('LLM_MAX_TURNS_PER_MINUTE', '30'))
_turns: deque[float] = deque()  # when the last model turns started


def record_llm_turn() -> None:
    _turns.append(time.time())


def _rate_limited() -> bool:
    while _turns and time.time() - _turns[0] > 60:
        _turns.popleft()
    return len(_turns) >= MAX_TURNS_PER_MINUTE


def record_llm_failure() -> None:
    """Record an LLM outage to temporarily route turns to script mode."""
    global _last_failure_timestamp
    _last_failure_timestamp = time.time()


def record_llm_success(estimated_cost: float = 0.0) -> None:
    """Record successful completion and accumulate budget tracking."""
    global _last_failure_timestamp, _estimated_spent_usd
    _last_failure_timestamp = 0.0
    _estimated_spent_usd += estimated_cost


def get_budget_status() -> dict[str, float]:
    """Report current spending and remaining cap."""
    return {
        'spent_usd': round(_estimated_spent_usd, 4),
        'cap_usd': HARD_BUDGET_CAP_USD,
        'remaining_usd': max(0.0, round(HARD_BUDGET_CAP_USD - _estimated_spent_usd, 4)),
    }


def get_openrouter_api_key() -> str:
    """Retrieve OpenRouter API key supporting openrouter_api_key, OPENROUTER_API_KEY, and .env files."""
    env_keys = ('openrouter_api_key', 'OPENROUTER_API_KEY', 'OPEN_ROUTER_API_KEY')
    has_explicit_env = False
    for key in env_keys:
        if key in os.environ:
            has_explicit_env = True
            val = os.environ[key]
            if val and val.strip():
                return val.strip()

    if has_explicit_env:
        return ''

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate_paths = [
        '.env',
        os.path.join(backend_dir, '.env'),
        os.path.join(os.path.dirname(backend_dir), '.env'),
        '../.env',
        'backend/.env',
    ]
    for env_path in candidate_paths:
        if os.path.isfile(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            k, v = k.strip(), v.strip().strip('"\'')
                            if k.lower() in ('openrouter_api_key', 'open_router_api_key'):
                                if v:
                                    return v
            except Exception:
                pass
    return ''


def route_turn(force_mode: str | None = None) -> str:
    """Determine whether to execute via OpenRouter LLM or Scripted fallback.
    Returns: 'llm' or 'script'
    """
    if force_mode in ('llm', 'script'):
        return force_mode

    # 1. Environment switch
    llm_enabled = os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes')
    if not llm_enabled:
        return 'script'

    # 2. Key presence (checks openrouter_api_key or OPENROUTER_API_KEY)
    api_key = get_openrouter_api_key()
    if not api_key:
        return 'script'

    # 3. Health window (failure in the last 60s -> fallback)
    if _last_failure_timestamp > 0 and (time.time() - _last_failure_timestamp) < LLM_HEALTH_TTL_SECONDS:
        return 'script'

    # 4. Budget cap check
    if _estimated_spent_usd >= HARD_BUDGET_CAP_USD:
        return 'script'

    # 5. Rate limit: more model turns than allowed in the last minute
    if _rate_limited():
        return 'script'

    return 'llm'


def agent_state() -> dict:
    """What answers the chat, and why: the provider and model when one is configured, else the reason the
    rule-based assistant is in use. Never the key."""
    enabled = os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes')
    configured = bool(get_openrouter_api_key())
    reason = (
        'disabled' if not enabled else
        'no_api_key' if not configured else
        'recent_failure' if _last_failure_timestamp > 0 and (time.time() - _last_failure_timestamp) < LLM_HEALTH_TTL_SECONDS else
        'budget_exhausted' if _estimated_spent_usd >= HARD_BUDGET_CAP_USD else
        'rate_limited' if _rate_limited() else
        None
    )
    labels = {
        None: 'AI model connected',
        'disabled': 'Rule-based assistant (AI model switched off)',
        'no_api_key': 'Rule-based assistant (no AI model configured)',
        'recent_failure': 'Rule-based assistant (the AI model did not answer; retrying shortly)',
        'budget_exhausted': 'Rule-based assistant (AI budget used up)',
        'rate_limited': 'Rule-based assistant (too many AI requests this minute)',
    }
    return {
        'mode': 'script' if reason else 'llm',
        'provider': 'openrouter' if configured else None,
        'model': os.getenv('OPENROUTER_MODEL', 'anthropic/claude-sonnet-5.5') if configured else None,
        'configured': configured,
        'enabled': enabled,
        'fallbackReason': reason,
        'label': labels[reason],
        # What the rule-based assistant is: a fixed set of requests matched on keywords, not language understanding.
        'capabilities': 'free-text questions, with tools and your confirmation before anything is saved' if not reason else 'a fixed set of requests: price a product, what-ifs, another period, explanations, memo, data check, sulphur break-even, document search',
    }

