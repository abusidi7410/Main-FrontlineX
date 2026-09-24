"""Centralized, Redis-backed rate limiting for the whole API.

Implemented as Django middleware (the single gateway), NOT inside views. It runs
once per request before the view resolver for every ``/api/`` URL and applies
one of three tiers — Auth, Standard, Expensive — using the **Sliding Window
Counter** algorithm. Counters live in Redis as a hash per key:

    rl:<tier>:<scope>  →  {win, prev, curr, ...expire}

so every server instance shares the same budget (multi-instance safe). The full
check-and-increment runs atomically inside one Lua script, so concurrent
instances can't overshoot the window. If Redis is unreachable the limiter fails
*open*: the request is allowed and a warning is logged (no Reddit-death).

Contract with clients:
    * Every limited response carries ``X-RateLimit-Limit``,
      ``X-RateLimit-Remaining`` and ``X-RateLimit-Reset``.
    * A rejected request returns ``429`` with ``Retry-After`` (seconds) and
      ``{"error": "Too many requests, please try again later"}``.
    * Every 429 is recorded through ``frontline.ratelimit`` (logger.warning)
      with IP / user id so abuse can be monitored.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger('frontline.ratelimit')

# Sliding Window Counter — one atomic Redis call.
#
# Redis stores for a key: the current window start, the previous-window count and
# the current-window count. For a request arriving at time ``now`` the estimated
# number of requests inside the *sliding* window is:
#
#     prev_count * (1 - weighted overlap of the current window) + curr_count
#
# Every worker runs the same script, so no coordination or mutex is needed.
_SLIDING_WINDOW_LUA = """
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local key    = KEYS[1]

local current_window = math.floor(now / window) * window

local prev_count = 0
local curr_count = 0
local window_start = current_window

local data = redis.call('HGETALL', key)
if data and #data > 0 then
  for i = 1, #data, 2 do
    if data[i] == 'win' then
      window_start = tonumber(data[i + 1])
    elseif data[i] == 'prev' then
      prev_count = tonumber(data[i + 1])
    elseif data[i] == 'curr' then
      curr_count = tonumber(data[i + 1])
    end
  end
end

-- Current fixed window rolled over: the previous window's counts become past.
if window_start < current_window then
  prev_count = curr_count
  curr_count = 0
  window_start = current_window
end

local elapsed = now - window_start
local weight = elapsed / window
-- Requests counted inside the last `window` seconds, before this request.
local estimated = prev_count * (1 - weight) + curr_count

local remaining = math.floor(limit - estimated)
local window_end = window_start + window
local reset = window_end - now

if remaining >= 1 then
  -- Allow: count this request and keep at least `reset` seconds of TTL.
  curr_count = curr_count + 1
  redis.call('HMSET', key,
    'win', window_start,
    'prev', prev_count,
    'curr', curr_count)
  redis.call('PEXPIRE', key, math.max(1, math.ceil(reset * 1000)))
  return {1, remaining - 1, reset}
end

-- Rejected: TTL still refreshed so an empty-but-pinned key can't leak.
redis.call('PEXPIRE', key, math.max(1, math.ceil(reset * 1000)))
return {0, remaining, reset}
"""


def _default_tiers():
    return {
        # Order matters: checked first -> last, so Specific beats Standard.
        'expensive': {
            'limit': 10,
            'window': 60,
            'prefixes': [
                '/api/v1/payments/',   # payment verification + record payments
                '/api/v1/otp/',        # OTP dispatch (reserved endpoint)
                '/api/v1/upload',      # file uploads (reserved endpoint)
            ],
        },
        'auth': {
            'limit': 5,
            'window': 60,
            'prefixes': [
                '/api/v1/auth/login',
                '/api/v1/auth/school/register',
            ],
        },
        'standard': {
            'limit': 60,
            'window': 60,
            'prefixes': ['/api/'],
        },
    }


APID_PATHS = ('/api/',)


class RateLimitMiddleware:
    """Global API rate limiter (Django 6 style middleware)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._redis_client = None
        self._redis_script = None
        self._last_warning_at = 0.0

    # ── Entry point ──────────────────────────────────────────────────────────

    def __call__(self, request):
        enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)
        if not enabled:
            return self.get_response(request)
        if not request.path.startswith(APID_PATHS):
            return self.get_response(request)

        tier_name, tier = self._resolve_tier(request.path)
        limit = int(tier['limit'])
        window = int(tier['window'])

        ip = self._client_ip(request)
        user_id = self._resolve_user_id(request)
        scope = user_id if tier_name != 'auth' else None
        key = self._key(tier_name, scope or ip)

        decision = self._evaluate(key, limit, window)
        if decision is None:
            # Fail-open: Redis unavailable — let the request through.
            return self.get_response(request)

        decision['tier'] = tier_name
        decision['user_id'] = user_id
        decision['ip'] = ip
        request._ratelimit = decision

        if decision['allowed']:
            response = self.get_response(request)
            self._set_headers(response, decision)
            return response

        self._log_exceeded(request, decision)
        response = JsonResponse(
            {'error': getattr(settings, 'RATE_LIMIT_ERROR_MESSAGE',
                              'Too many requests, please try again later')},
            status=429,
        )
        self._set_headers(response, decision)
        response['Retry-After'] = str(max(1, int(decision['reset'])))
        return response

    # ── Tier routing ─────────────────────────────────────────────────────────

    def _resolve_tier(self, path):
        """Pick the most specific matching tier (expensive > auth > standard)."""
        tiers = getattr(settings, 'RATE_LIMIT_TIERS', None) or _default_tiers()
        for name, tier in tiers.items():
            if name == 'standard':
                continue
            if any(path.startswith(prefix) for prefix in tier.get('prefixes', [])):
                return name, tier
        standard = tiers.get('standard', {'limit': 60, 'window': 60})
        return 'standard', standard

    # ── Identity ─────────────────────────────────────────────────────────────

    def _resolve_user_id(self, request):
        """Decode the JWT subject without a DB hit.

        DRF only authenticates inside the view, so the middleware reads the
        ``user_id`` claim directly from the ``Authorization`` bearer token. An
        invalid/expired token simply means "anonymous" → the IP is used.
        """
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            claim = getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_CLAIM', 'user_id')
            return str(AccessToken(header.split(' ', 1)[1]).payload.get(claim) or '')
        except Exception:
            return None

    def _client_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    @staticmethod
    def _key(tier, scope):
        return f'frontline:rl:{tier}:{scope}'

    # ── Redis interaction (fail-open) ────────────────────────────────────────

    def _evaluate(self, key, limit, window):
        """Run the atomic script. Returns a dict, or ``None`` on Redis failure."""
        client = self._get_client()
        if client is None:
            return None
        try:
            allowed, remaining, reset = self._script(client)(
                keys=[key], args=[int(time.time()), window, limit],
            )
            return {
                'allowed': int(allowed) == 1,
                'remaining': max(int(remaining), 0),
                'reset': max(int(reset), 0),
                'limit': limit,
                'window': window,
            }
        except Exception as exc:  # RedisError, timeouts, connection reset...
            self._warn(f'Redis unavailable for rate limiting, failing open: {exc!r}')
            return None

    def _get_client(self):
        if self._redis_client is not None:
            return self._redis_client
        url = getattr(settings, 'RATE_LIMIT_REDIS_URL', None)
        if not url:
            self._warn('RATE_LIMIT_REDIS_URL is not set; rate limiting disabled (fail-open).')
            return None
        try:
            import redis
            self._redis_client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_timeout=1,
                socket_connect_timeout=1,
                socket_keepalive=True,
                health_check_interval=30,
            )
        except Exception as exc:
            self._warn(f'Redis client failed to initialise, failing open: {exc!r}')
            return None
        return self._redis_client

    def _script(self, client):
        if self._redis_script is None:
            self._redis_script = client.register_script(_SLIDING_WINDOW_LUA)
        return self._redis_script

    def _warn(self, message):
        """Log a warning but never spam the log: at most once per 10 seconds."""
        now = time.time()
        if now - self._last_warning_at >= 10:
            logger.warning('%s', message)
            self._last_warning_at = now

    # ── Response contract ────────────────────────────────────────────────────

    @staticmethod
    def _set_headers(response, decision):
        response['X-RateLimit-Limit'] = str(decision['limit'])
        response['X-RateLimit-Remaining'] = str(int(decision['remaining']))
        response['X-RateLimit-Reset'] = str(int(decision['reset']))

    # ── Monitoring hook ──────────────────────────────────────────────────────

    @staticmethod
    def _log_exceeded(request, decision):
        logger.warning(
            'Rate limit exceeded: tier=%s key=%s ip=%s user_id=%s path=%s retry_after=%ss',
            decision['tier'],
            request.META.get('PATH_INFO', ''),
            decision['ip'],
            decision['user_id'] or '-',
            request.path,
            decision['reset'],
            extra={
                'tier': decision['tier'],
                'ip': decision['ip'],
                'user_id': decision['user_id'],
                'limit': decision['limit'],
                'remaining': decision['remaining'],
                'path': request.path,
            },
        )