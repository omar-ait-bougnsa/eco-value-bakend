"""Turn router & gatekeeper: selects LLM mode vs Scripted fallback."""
import os
import time

LLM_HEALTH_TTL_SECONDS = 60
HARD_BUDGET_CAP_USD = 40.0

# In-memory tracking of health and spending
_last_failure_timestamp: float = 0.0
_estimated_spent_usd: float = 0.0


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

    return 'llm'

