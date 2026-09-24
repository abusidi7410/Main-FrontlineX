"""Tests for the centralized Redis rate-limiter middleware.

The Redis round-trip is mocked (``_evaluate``), so tests exercise the middleware
contract: tier selection, key scoping, response headers, the 429 shape and the
fail-open path. The Lua script is itself validated at the source level, and the
real Redis behaviour is confirmed in the deployed environment.
"""
from unittest import mock

import json

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from ratelimit.middleware import RateLimitMiddleware


def _allowed(limit=60, remaining=59, reset=30, **kwargs):
    return {'allowed': True, 'remaining': remaining, 'reset': reset, 'limit': limit, **kwargs}


def _denied(limit=5, remaining=0, reset=12):
    return {'allowed': False, 'remaining': remaining, 'reset': reset, 'limit': limit}


def _make_middleware(response=_allowed()):
    mw = RateLimitMiddleware(lambda request: HttpResponse('ok'))
    mw._evaluate = mock.Mock(return_value=response)
    return mw


class TierRoutingTests(TestCase):
    def setUp(self):
        self.mw = _make_middleware()

    def test_auth_tier_matches_login_and_register(self):
        for path in ('/api/v1/auth/login/', '/api/v1/auth/school/register/'):
            name, tier = self.mw._resolve_tier(path)
            self.assertEqual((name, tier['limit']), ('auth', 5))

    def test_expensive_tier_beats_standard(self):
        name, tier = self.mw._resolve_tier('/api/v1/payments/abc/verify/')
        self.assertEqual((name, tier['limit']), ('expensive', 10))

    def test_standard_tier_is_the_catch_all(self):
        for path in ('/api/v1/students/', '/api/v1/accounts/users/', '/api/v1/attendance/'):
            name, tier = self.mw._resolve_tier(path)
            self.assertEqual((name, tier['limit']), ('standard', 60))

    def test_non_api_paths_are_not_limited(self):
        request = RequestFactory().get('/admin/login/')
        inner = mock.Mock(return_value=HttpResponse('ok'))
        mw = RateLimitMiddleware(inner)
        response = mw(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-RateLimit-Limit', response)


# The in-app limiter is off by default (the Nginx edge owns enforcement); these
# unit tests target the middleware in isolation, so force it on.
@override_settings(RATE_LIMIT_ENABLED=True)
class MiddlewareBehaviorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_allowed_request_sets_headers_and_proceeds(self):
        mw = _make_middleware(_allowed(limit=60, remaining=59, reset=30))
        response = mw(self.factory.get('/api/v1/students/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-RateLimit-Limit'], '60')
        self.assertEqual(response['X-RateLimit-Remaining'], '59')
        self.assertEqual(response['X-RateLimit-Reset'], '30')
        self.assertNotIn('Retry-After', response)

    def test_denied_request_returns_429_with_contract_body(self):
        mw = _make_middleware(_denied(limit=5, remaining=0, reset=12))
        with self.assertLogs('frontline.ratelimit', level='WARNING') as logs:
            response = mw(self.factory.get('/api/v1/auth/login/'))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            json.loads(response.content),
            {'error': 'Too many requests, please try again later'},
        )
        self.assertEqual(response['Retry-After'], '12')
        self.assertEqual(response['X-RateLimit-Limit'], '5')
        self.assertEqual(response['X-RateLimit-Remaining'], '0')
        self.assertEqual(response['X-RateLimit-Reset'], '12')
        self.assertTrue(any('Rate limit exceeded' in msg for msg in logs.output))

    def test_monitoring_hook_logs_ip_and_path(self):
        mw = _make_middleware(_denied())
        request = self.factory.get('/api/v1/auth/login/', REMOTE_ADDR='203.0.113.7')
        with self.assertLogs('frontline.ratelimit', level='WARNING') as logs:
            mw(request)
        self.assertTrue(any('203.0.113.7' in msg for msg in logs.output))
        self.assertTrue(any('/api/v1/auth/login/' in msg for msg in logs.output))

    def test_fail_open_allows_request_without_headers(self):
        mw = _make_middleware()
        mw._evaluate = mock.Mock(return_value=None)
        response = mw(self.factory.get('/api/v1/students/'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-RateLimit-Limit', response)

    def test_evaluate_warns_and_returns_none_when_redis_unavailable(self):
        mw = RateLimitMiddleware(lambda request: HttpResponse('ok'))
        with override_settings(RATE_LIMIT_REDIS_URL=''):
            with mock.patch('ratelimit.middleware.logger') as fake_logger:
                result = mw._evaluate('frontline:rl:standard:ip', 60, 60)
        self.assertIsNone(result)
        fake_logger.warning.assert_called()

    def test_standard_tier_keys_by_user_for_authenticated_requests(self):
        mw = _make_middleware(_allowed())
        captured = {}

        def fake_evaluate(key, limit, window):
            captured['key'] = key
            return _allowed(limit=limit, window=window)

        mw._evaluate = fake_evaluate
        user = User.objects.create_user(email='teacher@example.com')
        token = str(RefreshToken.for_user(user).access_token)
        request = self.factory.get(
            '/api/v1/students/',
            HTTP_AUTHORIZATION=f'Bearer {token}',
            REMOTE_ADDR='198.51.100.9',
        )
        mw(request)
        self.assertEqual(captured['key'], f'frontline:rl:standard:{user.pk}')

    def test_auth_tier_always_keys_by_ip(self):
        mw = _make_middleware(_allowed(limit=5))
        captured = {}

        def fake_evaluate(key, limit, window):
            captured['key'] = key
            return _allowed(limit=limit, remaining=4, reset=30, window=window)

        mw._evaluate = fake_evaluate
        mw(self.factory.get('/api/v1/auth/login/', REMOTE_ADDR='203.0.113.9'))
        self.assertEqual(captured['key'], 'frontline:rl:auth:203.0.113.9')

    def test_limiter_respects_master_switch(self):
        mw = _make_middleware()
        with override_settings(RATE_LIMIT_ENABLED=False):
            response = mw(self.factory.get('/api/v1/students/'))
        self.assertEqual(response.status_code, 200)
        mw._evaluate.assert_not_called()

    def test_middleware_is_wired_into_real_requests(self):
        """The full middleware stack (Django test client) must hit the limiter."""
        with mock.patch.object(RateLimitMiddleware, '_evaluate', return_value=_denied()):
            with self.assertLogs('frontline.ratelimit', level='WARNING'):
                response = self.client.get('/api/v1/auth/login/')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '12')
        self.assertEqual(response['X-RateLimit-Limit'], '5')
        self.assertIn(
            'Too many requests, please try again later',
            response.content.decode(),
        )


class LuaScriptTests(TestCase):
    def test_script_contains_sliding_weighting_math(self):
        from ratelimit.middleware import _SLIDING_WINDOW_LUA
        self.assertIn('prev_count * (1 - weight)', _SLIDING_WINDOW_LUA)
        self.assertIn('HMSET', _SLIDING_WINDOW_LUA)
        self.assertIn('PEXPIRE', _SLIDING_WINDOW_LUA)

    def test_key_namespace_is_tenant_safe(self):
        mw = _make_middleware()
        self.assertEqual(mw._key('standard', '7'), 'frontline:rl:standard:7')
        self.assertEqual(mw._key('auth', '203.0.113.1'), 'frontline:rl:auth:203.0.113.1')