# Pro Subscription Billing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in Fintank user buy Pro ($9.99/month or $71.88/year) through Stripe Checkout, manage or cancel it in the Stripe Customer Portal, and see their plan on a new `/subscription` page.

**Architecture:** A new Django app `billing` owns everything Stripe. `billing/gateway.py` is the only module that imports `stripe`; it returns plain values (`SubscriptionState`) so the rest is testable with `unittest.mock.patch`. `billing/sync.py` turns a Stripe subscription into `UserProfile` fields, driven by a signed webhook that always re-fetches the subscription (sync, not replay). The Next.js page talks to Django through one cookie-to-Bearer proxy route.

**Tech Stack:** Django 5 + DRF + simplejwt, `stripe` Python SDK (`StripeClient`, `client.v1.*`), Redis cache, Next.js Pages Router, react-bootstrap.

**Spec:** `docs/superpowers/specs/2026-10-13-pro-subscription-billing-design.md`

## Global Constraints

- Plans: Free (no Stripe), Pro monthly $9.99 USD (`STRIPE_PRICE_PRO_MONTHLY`), Pro yearly $71.88 USD (`STRIPE_PRICE_PRO_YEARLY`), shown as "$5.99/mo, billed $71.88 yearly".
- Pro unlocks only unlimited backtests (`backtester/quota.py` `UNLIMITED_TIERS = ('pro',)`). No new feature gating.
- Pro-granting statuses: `active`, `trialing`, `past_due`. Everything else → `free`.
- `backtest_quota_override` keeps precedence over tier (unchanged code in `quota.py`).
- Only `billing/gateway.py` imports `stripe`.
- Stripe API: `current_period_end` lives on `subscription["items"]["data"][0]`; fall back to the top-level field. Use subscript access (`obj["items"]`), never `obj.items` (that is `dict.items`).
- Never log request bodies, Stripe payloads, or keys.
- Run Django tests with the repo-root venv: `cd fintank/backend && ../../.venv/bin/python manage.py test <label>`. Postgres must be running (it already is for the existing suites).
- Do not start Django, Celery, `npm run dev`, or `stripe listen` — Franc starts servers. Name what is needed and stop.
- Files with CRLF line endings keep them: `src/pages/*.js` account pages, `src/scss/user/_user.scss`, `src/data/*.json` — check with `file <path>` before editing; edit with the Edit tool (preserves endings) and re-check.
- Do not `git commit` unless Franc asks. Steps below end at "tests pass", not at a commit.

---

## File Structure

**Backend (`fintank/backend/`)**

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | add `stripe` |
| `fintank_backend/settings.py` | add `billing` app, 4 env settings |
| `fintank_backend/urls.py` | include `billing.urls` under `api/` |
| `users/models.py` | 6 new `UserProfile` fields |
| `users/migrations/0004_*.py` | generated |
| `users/serializers.py` | new fields read-only |
| `users/admin.py` | new fields shown read-only |
| `billing/__init__.py`, `billing/apps.py` | app shell |
| `billing/gateway.py` | Stripe calls + `SubscriptionState` + errors |
| `billing/sync.py` | `tier_for_status`, `apply_subscription`, `handle_event` |
| `billing/plans.py` | cached Pro price amounts |
| `billing/views.py` | 3 DRF views + webhook view |
| `billing/urls.py` | routes |
| `billing/tests/test_gateway.py`, `test_sync.py`, `test_views.py`, `test_profile_fields.py` | tests |

**Frontend (`fintank/`)**

| File | Responsibility |
|------|----------------|
| `src/pages/api/billing/[action].js` | cookie → Bearer proxy for `subscription` / `checkout` / `portal` |
| `src/utils/subscriptionFormat.js` | pure formatting (amounts, dates, status note) |
| `src/hooks/useSubscription.js` | fetch + poll subscription |
| `src/pages/subscription.js` | the page |
| `src/data/user-account.json` | Subscription card |

---

### Task 1: Profile fields, settings and the `stripe` dependency

**Files:**
- Modify: `backend/pyproject.toml`, `backend/fintank_backend/settings.py`, `backend/users/models.py`, `backend/users/serializers.py`, `backend/users/admin.py`
- Create: `backend/users/migrations/0004_*.py` (generated), `backend/billing/__init__.py`, `backend/billing/apps.py`, `backend/billing/tests/__init__.py`, `backend/billing/tests/test_profile_fields.py`

**Interfaces:**
- Produces: `UserProfile.stripe_customer_id`, `.stripe_subscription_id`, `.subscription_status`, `.subscription_interval`, `.current_period_end`, `.cancel_at_period_end`; settings `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY`, `FRONTEND_URL`; installed app `billing`.

- [ ] **Step 1: Install `stripe` and confirm the client API shape**

```bash
cd /home/franc/projects/ai_agents/ai_tooling && uv pip install --python .venv/bin/python stripe
.venv/bin/python -c "import stripe; c = stripe.StripeClient('sk_test_x'); print(stripe.VERSION, c.v1.customers, c.v1.checkout.sessions, c.v1.billing_portal.sessions, c.v1.subscriptions, c.v1.prices, stripe.Webhook.construct_event, stripe.SignatureVerificationError, stripe.StripeError)"
```

Expected: a version string and six object reprs, no `AttributeError`. Note the major version `N`.

Add to `backend/pyproject.toml` `dependencies`, after `"requests>=2.32.5",`:

```toml
    "stripe>=N.0,<N+1",
```

(substitute the real major, e.g. `"stripe>=13.0,<14"`). Root `pyproject.toml` is Franc's uncommitted file — leave it alone; mention in the final report that `uv sync` at the repo root would remove `stripe` from `.venv` until it is added there too.

- [ ] **Step 2: Create the app shell**

`backend/billing/__init__.py`: empty.
`backend/billing/tests/__init__.py`: empty.

`backend/billing/apps.py`:

```python
from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
```

In `settings.py` `INSTALLED_APPS`, after `'backtester.apps.BacktesterConfig',` add:

```python
    'billing.apps.BillingConfig',
```

After `STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")` add:

```python
# Billing (billing/). The endpoints answer 503 until all of these are set,
# so a half-configured environment never charges anyone.
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_PRO_MONTHLY = os.getenv("STRIPE_PRICE_PRO_MONTHLY")
STRIPE_PRICE_PRO_YEARLY = os.getenv("STRIPE_PRICE_PRO_YEARLY")
# Where Stripe sends users back to, e.g. http://localhost:8020
FRONTEND_URL = os.getenv("FRONTEND_URL")
```

- [ ] **Step 3: Write the failing test**

`backend/billing/tests/test_profile_fields.py`:

```python
"""The billing fields exist, default to 'no subscription', and cannot be
written through the profile API -- only the webhook sets them."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import UserProfile

User = get_user_model()

BILLING_FIELDS = {
    'stripe_customer_id': 'cus_hacked',
    'stripe_subscription_id': 'sub_hacked',
    'subscription_status': 'active',
    'subscription_interval': 'year',
    'current_period_end': '2099-01-01T00:00:00Z',
    'cancel_at_period_end': True,
    'subscription_tier': 'pro',
}


def make_user(email='billing@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')
    UserProfile.objects.get_or_create(user=user)
    return user


class ProfileBillingFieldTests(TestCase):

    def test_a_new_profile_has_no_subscription(self):
        profile = make_user().userprofile
        self.assertIsNone(profile.stripe_customer_id)
        self.assertIsNone(profile.stripe_subscription_id)
        self.assertIsNone(profile.subscription_status)
        self.assertIsNone(profile.subscription_interval)
        self.assertIsNone(profile.current_period_end)
        self.assertFalse(profile.cancel_at_period_end)

    def test_billing_fields_cannot_be_patched_through_the_profile_api(self):
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)

        response = client.patch('/api/users/me/profile/update/', BILLING_FIELDS, format='json')

        self.assertLess(response.status_code, 500)
        profile = UserProfile.objects.get(user=user)
        self.assertIsNone(profile.stripe_customer_id)
        self.assertIsNone(profile.stripe_subscription_id)
        self.assertIsNone(profile.subscription_status)
        self.assertIsNone(profile.subscription_interval)
        self.assertIsNone(profile.current_period_end)
        self.assertFalse(profile.cancel_at_period_end)
        self.assertEqual(profile.subscription_tier, 'free')
```

- [ ] **Step 4: Run it and see it fail**

Run: `cd fintank/backend && ../../.venv/bin/python manage.py test billing.tests.test_profile_fields`
Expected: FAIL / ERROR — `AttributeError: 'UserProfile' object has no attribute 'stripe_customer_id'`.

- [ ] **Step 5: Add the fields**

In `users/models.py`, directly after `backtest_quota_override = models.PositiveIntegerField(null=True, blank=True)`:

```python
    # Billing (billing/). Written only by the Stripe webhook -- read-only in
    # UserProfileSerializer for the same reason as subscription_tier.
    # stripe_account_id above is a Stripe *Connect* account, a different thing.
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    subscription_status = models.CharField(max_length=32, null=True, blank=True)
    subscription_interval = models.CharField(max_length=8, null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
```

In `users/serializers.py` `UserProfileSerializer.Meta.extra_kwargs`, after `"backtest_quota_override": {"read_only": True},` add:

```python
            "stripe_customer_id": {"read_only": True},
            "stripe_subscription_id": {"read_only": True},
            "subscription_status": {"read_only": True},
            "subscription_interval": {"read_only": True},
            "current_period_end": {"read_only": True},
            "cancel_at_period_end": {"read_only": True},
```

In `users/admin.py`, in **both** `UserProfileInline` and `UserProfileAdmin`: add to `fields`, after `"stripe_account_id",`:

```python
        ("subscription_tier", "subscription_status", "subscription_interval"),
        ("current_period_end", "cancel_at_period_end"),
        ("stripe_customer_id", "stripe_subscription_id"),
```

and add to their `readonly_fields` tuples: `"subscription_status", "subscription_interval", "current_period_end", "cancel_at_period_end", "stripe_customer_id", "stripe_subscription_id"`. (`subscription_tier` stays editable so admins can still comp Pro.)

Generate the migration:

```bash
cd fintank/backend && ../../.venv/bin/python manage.py makemigrations users -n billing_fields
```

Expected: `users/migrations/0004_billing_fields.py` with 6 `AddField` operations and nothing else. If it contains other operations, stop and report — that means unrelated model drift.

- [ ] **Step 6: Run the tests and see them pass**

Run: `../../.venv/bin/python manage.py test billing.tests.test_profile_fields users`
Expected: all pass.

---

### Task 2: Stripe gateway

**Files:**
- Create: `backend/billing/gateway.py`, `backend/billing/tests/test_gateway.py`

**Interfaces:**
- Consumes: settings from Task 1.
- Produces:
  - `class BillingNotConfigured(Exception)`, `class StripeUnavailable(Exception)`, `class InvalidWebhook(Exception)`
  - `@dataclass(frozen=True) SubscriptionState(id: str, customer_id: str, status: str, interval: str | None, current_period_end: datetime | None, cancel_at_period_end: bool)`
  - `INTERVALS = ('month', 'year')`
  - `is_configured() -> bool`
  - `create_customer(email: str | None, user_id: int) -> str`
  - `create_checkout_url(customer_id: str, interval: str, user_id: int) -> str`
  - `create_portal_url(customer_id: str) -> str`
  - `retrieve_subscription(subscription_id: str) -> SubscriptionState`
  - `price_amount(interval: str) -> dict` → `{'amount': int, 'currency': str}`
  - `parse_event(payload: bytes, signature: str, secret: str)` → Stripe event (subscriptable)
  - `to_state(subscription) -> SubscriptionState`

- [ ] **Step 1: Write the failing tests**

`backend/billing/tests/test_gateway.py`:

```python
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import stripe
from django.test import SimpleTestCase, override_settings

from billing import gateway

CONFIGURED = dict(STRIPE_SECRET_KEY='sk_test_x', STRIPE_PRICE_PRO_MONTHLY='price_m',
                  STRIPE_PRICE_PRO_YEARLY='price_y', FRONTEND_URL='http://localhost:8020/')

SUB = {
    'id': 'sub_1', 'customer': 'cus_1', 'status': 'active', 'cancel_at_period_end': False,
    'items': {'data': [{'current_period_end': 1791849600,
                        'price': {'id': 'price_y', 'recurring': {'interval': 'year'}}}]},
}


def signed(payload: bytes, secret: str, at=None):
    at = int(at or time.time())
    sig = hmac.new(secret.encode(), f"{at}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={at},v1={sig}"


class ToStateTests(SimpleTestCase):

    def test_reads_the_period_end_from_the_first_item(self):
        state = gateway.to_state(SUB)
        self.assertEqual(state, gateway.SubscriptionState(
            id='sub_1', customer_id='cus_1', status='active', interval='year',
            current_period_end=datetime(2026, 10, 13, tzinfo=timezone.utc),
            cancel_at_period_end=False))

    def test_falls_back_to_the_legacy_top_level_period_end(self):
        legacy = dict(SUB, current_period_end=1791849600,
                      items={'data': [{'price': {'recurring': {'interval': 'month'}}}]})
        state = gateway.to_state(legacy)
        self.assertEqual(state.current_period_end, datetime(2026, 10, 13, tzinfo=timezone.utc))
        self.assertEqual(state.interval, 'month')

    def test_an_expanded_customer_object_gives_its_id(self):
        self.assertEqual(gateway.to_state(dict(SUB, customer={'id': 'cus_9'})).customer_id, 'cus_9')

    def test_works_on_a_real_stripe_object(self):
        obj = stripe.Subscription.construct_from(SUB, 'sk_test_x')
        self.assertEqual(gateway.to_state(obj).interval, 'year')

    def test_no_items_means_no_period_or_interval(self):
        state = gateway.to_state(dict(SUB, items={'data': []}))
        self.assertIsNone(state.current_period_end)
        self.assertIsNone(state.interval)


class ConfigTests(SimpleTestCase):

    @override_settings(**CONFIGURED)
    def test_configured_when_every_setting_is_present(self):
        self.assertTrue(gateway.is_configured())

    @override_settings(**dict(CONFIGURED, STRIPE_PRICE_PRO_YEARLY=None))
    def test_not_configured_when_any_setting_is_missing(self):
        self.assertFalse(gateway.is_configured())
        with self.assertRaises(gateway.BillingNotConfigured):
            gateway.create_portal_url('cus_1')


@override_settings(**CONFIGURED)
class CallTests(SimpleTestCase):

    def _client(self):
        client = MagicMock()
        patcher = patch.object(gateway.stripe, 'StripeClient', return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_checkout_uses_the_interval_price_and_return_urls(self):
        client = self._client()
        client.v1.checkout.sessions.create.return_value = {'url': 'https://checkout.stripe.com/x'}

        url = gateway.create_checkout_url('cus_1', 'year', 42)

        self.assertEqual(url, 'https://checkout.stripe.com/x')
        params = client.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(params['mode'], 'subscription')
        self.assertEqual(params['customer'], 'cus_1')
        self.assertEqual(params['client_reference_id'], '42')
        self.assertEqual(params['line_items'], [{'price': 'price_y', 'quantity': 1}])
        self.assertEqual(params['success_url'], 'http://localhost:8020/subscription?checkout=success')
        self.assertEqual(params['cancel_url'], 'http://localhost:8020/subscription?checkout=cancelled')

    def test_portal_returns_to_the_subscription_page(self):
        client = self._client()
        client.v1.billing_portal.sessions.create.return_value = {'url': 'https://billing.stripe.com/p'}

        self.assertEqual(gateway.create_portal_url('cus_1'), 'https://billing.stripe.com/p')
        params = client.v1.billing_portal.sessions.create.call_args.args[0]
        self.assertEqual(params, {'customer': 'cus_1',
                                  'return_url': 'http://localhost:8020/subscription'})

    def test_customer_carries_the_user_id(self):
        client = self._client()
        client.v1.customers.create.return_value = {'id': 'cus_new'}

        self.assertEqual(gateway.create_customer('a@b.co', 7), 'cus_new')
        params = client.v1.customers.create.call_args.args[0]
        self.assertEqual(params, {'email': 'a@b.co', 'metadata': {'user_id': '7'}})

    def test_price_amount(self):
        client = self._client()
        client.v1.prices.retrieve.return_value = {'unit_amount': 999, 'currency': 'usd'}

        self.assertEqual(gateway.price_amount('month'), {'amount': 999, 'currency': 'usd'})
        client.v1.prices.retrieve.assert_called_once_with('price_m')

    def test_stripe_errors_become_stripe_unavailable(self):
        client = self._client()
        client.v1.billing_portal.sessions.create.side_effect = stripe.StripeError('down')

        with self.assertRaises(gateway.StripeUnavailable):
            gateway.create_portal_url('cus_1')


class ParseEventTests(SimpleTestCase):
    SECRET = 'whsec_test'

    def test_a_correctly_signed_payload_parses(self):
        payload = json.dumps({'id': 'evt_1', 'object': 'event', 'type': 'customer.subscription.updated',
                              'data': {'object': {'id': 'sub_1'}}}).encode()

        event = gateway.parse_event(payload, signed(payload, self.SECRET), self.SECRET)

        self.assertEqual(event['type'], 'customer.subscription.updated')
        self.assertEqual(event['data']['object']['id'], 'sub_1')

    def test_a_wrong_signature_is_rejected(self):
        payload = b'{"id": "evt_1", "object": "event"}'
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(payload, signed(payload, 'whsec_other'), self.SECRET)

    def test_a_missing_signature_is_rejected(self):
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(b'{}', '', self.SECRET)

    def test_an_old_signature_is_rejected(self):
        payload = b'{"id": "evt_1", "object": "event"}'
        with self.assertRaises(gateway.InvalidWebhook):
            gateway.parse_event(payload, signed(payload, self.SECRET, at=time.time() - 3600), self.SECRET)
```

Note: `1791849600` is `2026-10-13T00:00:00Z`. Verify once with `python -c "import datetime;print(datetime.datetime.fromtimestamp(1791849600, datetime.timezone.utc))"` and correct the expected datetime in the tests if it differs.

- [ ] **Step 2: Run them and see them fail**

Run: `../../.venv/bin/python manage.py test billing.tests.test_gateway`
Expected: ERROR — `ImportError: cannot import name 'gateway'`.

- [ ] **Step 3: Implement the gateway**

`backend/billing/gateway.py`:

```python
"""The only module that talks to Stripe.

Everything else in billing/ calls these functions and works with the plain
SubscriptionState they return, so tests patch this module instead of the SDK.
Stripe objects are read by subscript (`obj["items"]`), never by attribute:
`obj.items` is dict.items on a StripeObject.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps

import stripe
from django.conf import settings

INTERVALS = ('month', 'year')
REQUIRED_SETTINGS = ('STRIPE_SECRET_KEY', 'STRIPE_PRICE_PRO_MONTHLY',
                     'STRIPE_PRICE_PRO_YEARLY', 'FRONTEND_URL')


class BillingNotConfigured(Exception):
    """A billing setting is missing; the endpoints answer 503."""


class StripeUnavailable(Exception):
    """Stripe rejected or failed the call; the endpoints answer 502."""


class InvalidWebhook(Exception):
    """The webhook payload or its signature did not verify."""


@dataclass(frozen=True)
class SubscriptionState:
    id: str
    customer_id: str
    status: str
    interval: str | None
    current_period_end: datetime | None
    cancel_at_period_end: bool


def is_configured() -> bool:
    return all(getattr(settings, name, None) for name in REQUIRED_SETTINGS)


def _client():
    if not is_configured():
        raise BillingNotConfigured()
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def _price_id(interval: str) -> str:
    return {'month': settings.STRIPE_PRICE_PRO_MONTHLY,
            'year': settings.STRIPE_PRICE_PRO_YEARLY}[interval]


def _frontend(path: str) -> str:
    return settings.FRONTEND_URL.rstrip('/') + path


def _stripe_call(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except stripe.StripeError as exc:
            # The message is Stripe's own; never includes the key.
            raise StripeUnavailable(str(exc)) from exc
    return wrapper


def _id(value):
    return value if isinstance(value, str) else value['id']


@_stripe_call
def create_customer(email, user_id) -> str:
    params = {'metadata': {'user_id': str(user_id)}}
    if email:
        params['email'] = email
    return _client().v1.customers.create(params)['id']


@_stripe_call
def create_checkout_url(customer_id: str, interval: str, user_id) -> str:
    session = _client().v1.checkout.sessions.create({
        'mode': 'subscription',
        'customer': customer_id,
        'client_reference_id': str(user_id),
        'line_items': [{'price': _price_id(interval), 'quantity': 1}],
        'success_url': _frontend('/subscription?checkout=success'),
        'cancel_url': _frontend('/subscription?checkout=cancelled'),
    })
    return session['url']


@_stripe_call
def create_portal_url(customer_id: str) -> str:
    session = _client().v1.billing_portal.sessions.create({
        'customer': customer_id,
        'return_url': _frontend('/subscription'),
    })
    return session['url']


@_stripe_call
def retrieve_subscription(subscription_id: str) -> SubscriptionState:
    return to_state(_client().v1.subscriptions.retrieve(subscription_id))


@_stripe_call
def price_amount(interval: str) -> dict:
    price = _client().v1.prices.retrieve(_price_id(interval))
    return {'amount': price['unit_amount'], 'currency': price['currency']}


def parse_event(payload: bytes, signature: str, secret: str):
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise InvalidWebhook() from exc


def to_state(subscription) -> SubscriptionState:
    items = (subscription.get('items') or {}).get('data') or []
    first = items[0] if items else {}
    # API 2025-03-31.basil moved the billing period onto the items.
    period_end = first.get('current_period_end') or subscription.get('current_period_end')
    recurring = (first.get('price') or {}).get('recurring') or {}
    return SubscriptionState(
        id=subscription['id'],
        customer_id=_id(subscription['customer']),
        status=subscription['status'],
        interval=recurring.get('interval'),
        current_period_end=(datetime.fromtimestamp(period_end, tz=timezone.utc)
                            if period_end else None),
        cancel_at_period_end=bool(subscription.get('cancel_at_period_end')),
    )
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `../../.venv/bin/python manage.py test billing.tests.test_gateway`
Expected: all pass. If `test_works_on_a_real_stripe_object` fails on `.get`, replace `x.get(k)` in `to_state` with a helper `def _get(obj, key): try: return obj[key] except (KeyError, TypeError): return None` and use it everywhere in `to_state`.

---

### Task 3: Sync — tier rule and webhook event handling

**Files:**
- Create: `backend/billing/sync.py`, `backend/billing/tests/test_sync.py`

**Interfaces:**
- Consumes: `gateway.SubscriptionState`, `gateway.retrieve_subscription`, profile fields from Task 1.
- Produces:
  - `PRO_STATUSES: frozenset[str]`
  - `tier_for_status(status: str | None) -> str` → `'pro' | 'free'`
  - `apply_subscription(state: SubscriptionState, user_id=None) -> bool` (True when written)
  - `HANDLED_EVENTS: frozenset[str]`
  - `handle_event(event) -> None`

- [ ] **Step 1: Write the failing tests**

`backend/billing/tests/test_sync.py`:

```python
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase, override_settings

from backtester.quota import get_quota
from billing import sync
from billing.gateway import SubscriptionState
from billing.tests.test_profile_fields import make_user
from users.models import UserProfile

END = datetime(2026, 11, 13, tzinfo=timezone.utc)


def state(**overrides):
    base = dict(id='sub_1', customer_id='cus_1', status='active', interval='month',
                current_period_end=END, cancel_at_period_end=False)
    base.update(overrides)
    return SubscriptionState(**base)


def event(kind, obj):
    return {'type': kind, 'data': {'object': obj}}


class TierForStatusTests(TestCase):

    def test_pro_granting_statuses(self):
        for status in ('active', 'trialing', 'past_due'):
            self.assertEqual(sync.tier_for_status(status), 'pro', status)

    def test_everything_else_is_free(self):
        for status in ('canceled', 'unpaid', 'incomplete', 'incomplete_expired',
                       'paused', None, ''):
            self.assertEqual(sync.tier_for_status(status), 'free', status)


class ApplySubscriptionTests(TestCase):

    def setUp(self):
        self.user = make_user()
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id='cus_1')

    def profile(self):
        return UserProfile.objects.get(user=self.user)

    def test_an_active_subscription_makes_the_user_pro(self):
        self.assertTrue(sync.apply_subscription(state()))

        p = self.profile()
        self.assertEqual(p.subscription_tier, 'pro')
        self.assertEqual(p.stripe_subscription_id, 'sub_1')
        self.assertEqual(p.subscription_status, 'active')
        self.assertEqual(p.subscription_interval, 'month')
        self.assertEqual(p.current_period_end, END)
        self.assertFalse(p.cancel_at_period_end)

    def test_a_pending_cancellation_keeps_pro_until_the_period_ends(self):
        sync.apply_subscription(state(cancel_at_period_end=True))
        p = self.profile()
        self.assertEqual(p.subscription_tier, 'pro')
        self.assertTrue(p.cancel_at_period_end)

    def test_a_cancelled_subscription_drops_the_user_to_free(self):
        sync.apply_subscription(state())
        sync.apply_subscription(state(status='canceled'))
        self.assertEqual(self.profile().subscription_tier, 'free')

    def test_applying_the_same_state_twice_is_harmless(self):
        sync.apply_subscription(state())
        sync.apply_subscription(state())
        self.assertEqual(self.profile().subscription_tier, 'pro')

    def test_an_unknown_customer_writes_nothing(self):
        self.assertFalse(sync.apply_subscription(state(customer_id='cus_nobody')))
        self.assertEqual(self.profile().subscription_tier, 'free')

    def test_falls_back_to_the_user_id_from_checkout(self):
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id=None)
        self.assertTrue(sync.apply_subscription(state(), user_id=str(self.user.pk)))
        self.assertEqual(self.profile().stripe_customer_id, 'cus_1')

    def test_the_user_id_fallback_never_moves_a_profile_to_another_customer(self):
        self.assertFalse(sync.apply_subscription(state(customer_id='cus_other'),
                                                 user_id=str(self.user.pk)))
        self.assertEqual(self.profile().stripe_customer_id, 'cus_1')

    def test_a_garbage_user_id_is_ignored(self):
        self.assertFalse(sync.apply_subscription(state(customer_id='cus_nobody'), user_id='abc'))

    def test_a_second_live_subscription_is_not_adopted(self):
        sync.apply_subscription(state())
        with self.assertLogs('billing.sync', level='ERROR'):
            self.assertFalse(sync.apply_subscription(state(id='sub_2')))
        self.assertEqual(self.profile().stripe_subscription_id, 'sub_1')

    def test_an_old_subscription_ending_does_not_downgrade_the_live_one(self):
        sync.apply_subscription(state(id='sub_2'))
        self.assertFalse(sync.apply_subscription(state(id='sub_1', status='canceled')))
        p = self.profile()
        self.assertEqual(p.stripe_subscription_id, 'sub_2')
        self.assertEqual(p.subscription_tier, 'pro')

    def test_a_new_subscription_replaces_a_finished_one(self):
        sync.apply_subscription(state(status='canceled'))
        self.assertTrue(sync.apply_subscription(state(id='sub_2')))
        self.assertEqual(self.profile().stripe_subscription_id, 'sub_2')

    @override_settings(FREE_TIER_BACKTEST_LIMIT=3)
    def test_upgrade_and_cancellation_move_the_backtest_limit(self):
        self.assertEqual(get_quota(self.user).limit, 3)
        sync.apply_subscription(state())
        self.assertIsNone(get_quota(self.user).limit)
        sync.apply_subscription(state(status='canceled'))
        self.assertEqual(get_quota(self.user).limit, 3)


class HandleEventTests(TestCase):

    def setUp(self):
        self.user = make_user()
        UserProfile.objects.filter(user=self.user).update(stripe_customer_id='cus_1')

    def test_subscription_events_refetch_the_subscription(self):
        for kind in ('customer.subscription.created', 'customer.subscription.updated',
                     'customer.subscription.deleted'):
            with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get:
                sync.handle_event(event(kind, {'id': 'sub_1', 'customer': 'cus_1', 'status': 'stale'}))
            get.assert_called_once_with('sub_1')

    def test_the_stored_state_comes_from_stripe_not_the_payload(self):
        with patch('billing.sync.gateway.retrieve_subscription',
                   return_value=state(status='canceled')):
            sync.handle_event(event('customer.subscription.updated',
                                    {'id': 'sub_1', 'status': 'active'}))
        self.assertEqual(UserProfile.objects.get(user=self.user).subscription_tier, 'free')

    def test_checkout_completed_uses_the_session_subscription_and_user(self):
        with patch('billing.sync.gateway.retrieve_subscription', return_value=state()) as get, \
             patch('billing.sync.apply_subscription') as apply:
            sync.handle_event(event('checkout.session.completed',
                                    {'subscription': 'sub_1', 'client_reference_id': '5'}))
        get.assert_called_once_with('sub_1')
        apply.assert_called_once_with(state(), user_id='5')

    def test_checkout_without_a_subscription_is_ignored(self):
        with patch('billing.sync.gateway.retrieve_subscription') as get:
            sync.handle_event(event('checkout.session.completed', {'subscription': None}))
        get.assert_not_called()

    def test_unhandled_events_are_ignored(self):
        with patch('billing.sync.gateway.retrieve_subscription') as get:
            sync.handle_event(event('invoice.paid', {'id': 'in_1'}))
        get.assert_not_called()
```

- [ ] **Step 2: Run them and see them fail**

Run: `../../.venv/bin/python manage.py test billing.tests.test_sync`
Expected: ERROR — `cannot import name 'sync'`.

- [ ] **Step 3: Implement**

`backend/billing/sync.py`:

```python
"""Turns Stripe subscription state into UserProfile fields.

Every handled webhook re-fetches the subscription from Stripe and writes its
current state, so duplicate and out-of-order deliveries converge on the right
answer without an event log.
"""
import logging

from django.db import transaction

from users.models import UserProfile

from . import gateway

logger = logging.getLogger(__name__)

# past_due keeps Pro while Stripe retries the card.
PRO_STATUSES = frozenset({'active', 'trialing', 'past_due'})

HANDLED_EVENTS = frozenset({
    'checkout.session.completed',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
})


def tier_for_status(status) -> str:
    return 'pro' if status in PRO_STATUSES else 'free'


def _find_profile(customer_id, user_id):
    profile = UserProfile.objects.filter(stripe_customer_id=customer_id).first()
    if profile is None and user_id is not None and str(user_id).isdigit():
        profile = UserProfile.objects.filter(user_id=int(user_id)).first()
    return profile


def apply_subscription(state: gateway.SubscriptionState, user_id=None) -> bool:
    found = _find_profile(state.customer_id, user_id)
    if found is None:
        logger.warning("Stripe subscription %s for unknown customer %s", state.id, state.customer_id)
        return False

    with transaction.atomic():
        profile = UserProfile.objects.select_for_update().get(pk=found.pk)

        if profile.stripe_customer_id and profile.stripe_customer_id != state.customer_id:
            logger.error("Subscription %s is for customer %s but user %s is customer %s; not applied",
                         state.id, state.customer_id, profile.user_id, profile.stripe_customer_id)
            return False

        tracked = profile.stripe_subscription_id
        if tracked and tracked != state.id and tier_for_status(profile.subscription_status) == 'pro':
            if tier_for_status(state.status) == 'pro':
                logger.error("User %s has a second live subscription %s; keeping %s. "
                             "Cancel and refund %s in Stripe.",
                             profile.user_id, state.id, tracked, state.id)
            return False

        profile.stripe_customer_id = state.customer_id
        profile.stripe_subscription_id = state.id
        profile.subscription_status = state.status
        profile.subscription_interval = state.interval
        profile.current_period_end = state.current_period_end
        profile.cancel_at_period_end = state.cancel_at_period_end
        profile.subscription_tier = tier_for_status(state.status)
        profile.save(update_fields=[
            'stripe_customer_id', 'stripe_subscription_id', 'subscription_status',
            'subscription_interval', 'current_period_end', 'cancel_at_period_end',
            'subscription_tier', 'updated_at',
        ])
    return True


def handle_event(event) -> None:
    kind = event['type']
    if kind not in HANDLED_EVENTS:
        return

    obj = event['data']['object']
    if kind == 'checkout.session.completed':
        subscription = obj.get('subscription')
        user_id = obj.get('client_reference_id')
        if not subscription:
            return
    else:
        subscription = obj['id']
        user_id = None

    subscription_id = subscription if isinstance(subscription, str) else subscription['id']
    apply_subscription(gateway.retrieve_subscription(subscription_id), user_id=user_id)
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `../../.venv/bin/python manage.py test billing.tests.test_sync backtester.tests.test_quota`
Expected: all pass.

---

### Task 4: Endpoints, plans cache and URLs

**Files:**
- Create: `backend/billing/plans.py`, `backend/billing/views.py`, `backend/billing/urls.py`, `backend/billing/tests/test_views.py`
- Modify: `backend/fintank_backend/urls.py`

**Interfaces:**
- Consumes: everything in `gateway` and `sync`.
- Produces: `GET /api/billing/subscription/`, `POST /api/billing/checkout/`, `POST /api/billing/portal/`, `POST /api/billing/webhook/`; `plans.get_plans() -> dict | None`; `plans.PLANS_CACHE_KEY = 'billing:plans:v1'`.
- Subscription response (consumed by Task 5): `{tier, status, interval, current_period_end (ISO string|null), cancel_at_period_end, has_billing_account, plans: {month: {amount, currency}, year: {...}} | null}`. Errors: `{detail: str}`.

- [ ] **Step 1: Write the failing tests**

`backend/billing/tests/test_views.py`:

```python
from datetime import datetime, timezone
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from billing import gateway, plans
from billing.tests.test_gateway import CONFIGURED
from billing.tests.test_profile_fields import make_user
from users.models import UserProfile

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PLANS = {'month': {'amount': 999, 'currency': 'usd'}, 'year': {'amount': 7188, 'currency': 'usd'}}


@override_settings(CACHES=LOCMEM, **CONFIGURED)
class ViewTestCase(TestCase):

    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def set_profile(self, **fields):
        UserProfile.objects.filter(user=self.user).update(**fields)


class SubscriptionViewTests(ViewTestCase):

    def test_a_free_user(self):
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertEqual(data, {
            'tier': 'free', 'status': None, 'interval': None, 'current_period_end': None,
            'cancel_at_period_end': False, 'has_billing_account': False, 'plans': PLANS,
        })

    def test_a_pro_user(self):
        self.set_profile(subscription_tier='pro', subscription_status='active',
                         subscription_interval='year', stripe_customer_id='cus_1',
                         current_period_end=datetime(2027, 10, 13, tzinfo=timezone.utc))
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertEqual(data['tier'], 'pro')
        self.assertEqual(data['interval'], 'year')
        self.assertTrue(data['has_billing_account'])
        self.assertTrue(data['current_period_end'].startswith('2027-10-13T00:00:00'))

    def test_plans_are_cached(self):
        with patch('billing.plans.gateway.price_amount', side_effect=lambda i: PLANS[i]) as price:
            self.client.get('/api/billing/subscription/')
            self.client.get('/api/billing/subscription/')
        self.assertEqual(price.call_count, 2)  # month + year, once

    def test_plans_are_null_when_stripe_is_down_and_not_cached(self):
        with patch('billing.plans.gateway.price_amount', side_effect=gateway.StripeUnavailable('x')):
            data = self.client.get('/api/billing/subscription/').json()
        self.assertIsNone(data['plans'])
        self.assertIsNone(cache.get(plans.PLANS_CACHE_KEY))

    @override_settings(STRIPE_PRICE_PRO_MONTHLY=None)
    def test_unconfigured_billing_still_shows_the_tier(self):
        response = self.client.get('/api/billing/subscription/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['plans'])

    def test_requires_login(self):
        self.assertEqual(APIClient().get('/api/billing/subscription/').status_code, 401)


class CheckoutViewTests(ViewTestCase):

    def test_creates_the_customer_once_and_returns_the_checkout_url(self):
        with patch('billing.views.gateway.create_customer', return_value='cus_new') as customer, \
             patch('billing.views.gateway.create_checkout_url', return_value='https://co/x') as checkout:
            first = self.client.post('/api/billing/checkout/', {'interval': 'year'}, format='json')
            second = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')

        self.assertEqual(first.json(), {'url': 'https://co/x'})
        self.assertEqual(second.status_code, 200)
        customer.assert_called_once_with(self.user.email, self.user.pk)
        checkout.assert_any_call('cus_new', 'year', self.user.pk)
        self.assertEqual(UserProfile.objects.get(user=self.user).stripe_customer_id, 'cus_new')

    def test_a_bad_interval_is_400(self):
        response = self.client.post('/api/billing/checkout/', {'interval': 'week'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_an_existing_live_subscription_is_409(self):
        self.set_profile(subscription_status='past_due', stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_checkout_url') as checkout:
            response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 409)
        checkout.assert_not_called()

    def test_stripe_failure_is_502(self):
        self.set_profile(stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_checkout_url',
                   side_effect=gateway.StripeUnavailable('x')):
            response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 502)

    @override_settings(FRONTEND_URL=None)
    def test_unconfigured_billing_is_503(self):
        response = self.client.post('/api/billing/checkout/', {'interval': 'month'}, format='json')
        self.assertEqual(response.status_code, 503)


class PortalViewTests(ViewTestCase):

    def test_no_billing_account_is_409(self):
        self.assertEqual(self.client.post('/api/billing/portal/').status_code, 409)

    def test_returns_the_portal_url(self):
        self.set_profile(stripe_customer_id='cus_1')
        with patch('billing.views.gateway.create_portal_url', return_value='https://bp/x') as portal:
            response = self.client.post('/api/billing/portal/')
        self.assertEqual(response.json(), {'url': 'https://bp/x'})
        portal.assert_called_once_with('cus_1')


@override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
class WebhookViewTests(ViewTestCase):

    def post(self, body=b'{}', signature='t=1,v1=x'):
        return APIClient().post('/api/billing/webhook/', body, content_type='application/json',
                                HTTP_STRIPE_SIGNATURE=signature)

    def test_a_bad_signature_is_400_and_nothing_is_handled(self):
        with patch('billing.views.gateway.parse_event', side_effect=gateway.InvalidWebhook()), \
             patch('billing.views.sync.handle_event') as handle:
            self.assertEqual(self.post().status_code, 400)
        handle.assert_not_called()

    def test_a_verified_event_is_handled(self):
        evt = {'type': 'customer.subscription.updated', 'data': {'object': {'id': 'sub_1'}}}
        with patch('billing.views.gateway.parse_event', return_value=evt) as parse, \
             patch('billing.views.sync.handle_event') as handle:
            response = self.post(b'{"x": 1}', 'sig')
        self.assertEqual(response.status_code, 200)
        parse.assert_called_once_with(b'{"x": 1}', 'sig', 'whsec_test')
        handle.assert_called_once_with(evt)

    def test_an_unexpected_error_is_500_so_stripe_retries(self):
        with patch('billing.views.gateway.parse_event', return_value={'type': 'x'}), \
             patch('billing.views.sync.handle_event', side_effect=RuntimeError('boom')):
            self.assertEqual(self.post().status_code, 500)

    def test_a_stripe_outage_while_syncing_is_500(self):
        with patch('billing.views.gateway.parse_event', return_value={'type': 'x'}), \
             patch('billing.views.sync.handle_event', side_effect=gateway.StripeUnavailable('x')):
            self.assertEqual(self.post().status_code, 500)

    @override_settings(STRIPE_WEBHOOK_SECRET=None)
    def test_without_a_webhook_secret_it_is_503(self):
        self.assertEqual(self.post().status_code, 503)

    def test_get_is_not_allowed(self):
        self.assertEqual(APIClient().get('/api/billing/webhook/').status_code, 405)
```

- [ ] **Step 2: Run them and see them fail**

Run: `../../.venv/bin/python manage.py test billing.tests.test_views`
Expected: FAIL — 404s / import errors for `billing.plans`.

- [ ] **Step 3: Implement**

`backend/billing/plans.py`:

```python
"""Pro prices as Stripe will charge them, cached so the page doesn't call
Stripe on every load. A failure is not cached: the next load retries."""
import logging

from django.core.cache import cache

from . import gateway

logger = logging.getLogger(__name__)

PLANS_CACHE_KEY = 'billing:plans:v1'
PLANS_TTL = 3600


def get_plans():
    cached = cache.get(PLANS_CACHE_KEY)
    if cached:
        return cached
    try:
        plans = {interval: gateway.price_amount(interval) for interval in gateway.INTERVALS}
    except (gateway.StripeUnavailable, gateway.BillingNotConfigured):
        logger.warning("Could not load Pro prices from Stripe", exc_info=True)
        return None
    cache.set(PLANS_CACHE_KEY, plans, PLANS_TTL)
    return plans
```

`backend/billing/views.py`:

```python
import logging

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import UserProfile

from . import gateway, plans, sync

logger = logging.getLogger(__name__)

NOT_CONFIGURED = {'detail': 'Billing is not available right now.'}
STRIPE_DOWN = {'detail': 'Could not reach the payment provider. Please try again.'}


def _profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_view(request):
    profile = _profile(request.user)
    return Response({
        'tier': profile.subscription_tier or 'free',
        'status': profile.subscription_status,
        'interval': profile.subscription_interval,
        'current_period_end': profile.current_period_end,
        'cancel_at_period_end': profile.cancel_at_period_end,
        'has_billing_account': bool(profile.stripe_customer_id),
        'plans': plans.get_plans() if gateway.is_configured() else None,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkout_view(request):
    if not gateway.is_configured():
        return Response(NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    interval = request.data.get('interval')
    if interval not in gateway.INTERVALS:
        return Response({'detail': 'Choose a monthly or yearly plan.'},
                        status=status.HTTP_400_BAD_REQUEST)

    profile = _profile(request.user)
    if sync.tier_for_status(profile.subscription_status) == 'pro':
        return Response({'detail': 'You already have Pro. Manage it from the billing portal.'},
                        status=status.HTTP_409_CONFLICT)

    try:
        # Locked so two quick clicks can't create two Stripe customers.
        with transaction.atomic():
            profile = UserProfile.objects.select_for_update().get(pk=profile.pk)
            if not profile.stripe_customer_id:
                profile.stripe_customer_id = gateway.create_customer(request.user.email, request.user.pk)
                profile.save(update_fields=['stripe_customer_id', 'updated_at'])
        url = gateway.create_checkout_url(profile.stripe_customer_id, interval, request.user.pk)
    except gateway.StripeUnavailable:
        logger.warning("Checkout session failed for user %s", request.user.pk, exc_info=True)
        return Response(STRIPE_DOWN, status=status.HTTP_502_BAD_GATEWAY)
    return Response({'url': url})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def portal_view(request):
    if not gateway.is_configured():
        return Response(NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    profile = _profile(request.user)
    if not profile.stripe_customer_id:
        return Response({'detail': 'You do not have a subscription to manage yet.'},
                        status=status.HTTP_409_CONFLICT)
    try:
        url = gateway.create_portal_url(profile.stripe_customer_id)
    except gateway.StripeUnavailable:
        logger.warning("Portal session failed for user %s", request.user.pk, exc_info=True)
        return Response(STRIPE_DOWN, status=status.HTTP_502_BAD_GATEWAY)
    return Response({'url': url})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe calls this directly. Plain Django view, not DRF: the signature is
    over the raw body, which DRF's parsers would consume first."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret or not gateway.is_configured():
        return JsonResponse(NOT_CONFIGURED, status=503)

    try:
        event = gateway.parse_event(request.body, request.headers.get('Stripe-Signature', ''), secret)
    except gateway.InvalidWebhook:
        return JsonResponse({'detail': 'Invalid signature.'}, status=400)

    try:
        sync.handle_event(event)
    except Exception:
        # 500 makes Stripe retry later. Log the type only, never the payload.
        logger.exception("Stripe webhook %s failed", event.get('type'))
        return JsonResponse({'detail': 'Webhook processing failed.'}, status=500)
    return JsonResponse({'received': True})
```

`backend/billing/urls.py`:

```python
"""Every app mounts at path("api/", include(...)), so routes carry billing/."""
from django.urls import path

from . import views

urlpatterns = [
    path('billing/subscription/', views.subscription_view, name='billing_subscription'),
    path('billing/checkout/', views.checkout_view, name='billing_checkout'),
    path('billing/portal/', views.portal_view, name='billing_portal'),
    path('billing/webhook/', views.stripe_webhook, name='billing_webhook'),
]
```

In `fintank_backend/urls.py`, after `path("api/", include("backtester.urls")),` add:

```python
    path("api/", include("billing.urls")),
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `../../.venv/bin/python manage.py test billing`
Expected: all billing tests pass.

Note: `test_requires_login` expects 401 because `JWTAuthentication` sends a `WWW-Authenticate` header; if it returns 403, check `REST_FRAMEWORK` auth classes before changing the assertion.

- [ ] **Step 5: Run the neighbouring suites**

Run: `../../.venv/bin/python manage.py test users backtester billing`
Expected: all pass (backtester had 278 before this work).

---

### Task 5: Frontend — proxy, formatting, page and account card

**Files:**
- Create: `src/pages/api/billing/[action].js`, `src/utils/subscriptionFormat.js`, `src/hooks/useSubscription.js`, `src/pages/subscription.js`
- Modify: `src/data/user-account.json`

**Interfaces:**
- Consumes: the Task 4 endpoints and response shape.
- Produces: route `/subscription`; `formatAmount(cents, currency)`, `perMonth(yearCents)`, `formatPlanDate(iso)`, `statusNote(sub)`; `useSubscription({ poll })` → `{ subscription, loading, error, reload }`.

- [ ] **Step 1: Write the failing formatting test**

The repo has no JS test runner. Use a scratch harness: `$S` is the session scratchpad (`/tmp/claude-1000/-home-franc-projects-ai-agents-ai-tooling-fintank/<session>/scratchpad`).

`$S/subfmt.test.mjs`:

```js
import * as f from './subfmt.mjs'
const eq = (a, b) => console.log(a === b ? 'ok  ' : 'FAIL', JSON.stringify(a), '|', JSON.stringify(b))

eq(f.formatAmount(999, 'usd'), '$9.99')
eq(f.formatAmount(7188, 'usd'), '$71.88')
eq(f.formatAmount(null, 'usd'), null)
eq(f.perMonth(7188), 599)
eq(f.formatPlanDate('2027-10-13T00:00:00Z'), 'October 13, 2027')
eq(f.formatPlanDate(null), null)
eq(f.statusNote({ tier: 'free' }), null)
eq(f.statusNote({ tier: 'pro', status: 'active', current_period_end: '2027-10-13T00:00:00Z' }).text,
   'Renews on October 13, 2027.')
eq(f.statusNote({ tier: 'pro', status: 'active', cancel_at_period_end: true, current_period_end: '2027-10-13T00:00:00Z' }).text,
   'Your subscription is cancelled. Pro ends on October 13, 2027.')
eq(f.statusNote({ tier: 'pro', status: 'past_due' }).variant, 'warning')
eq(f.statusNote({ tier: 'pro', status: null }).text, 'Pro was added to your account by Fintank.')
```

Run: `cp src/utils/subscriptionFormat.js $S/subfmt.mjs && node $S/subfmt.test.mjs`
Expected: `cp` fails — file does not exist.

- [ ] **Step 2: Implement the formatter**

`src/utils/subscriptionFormat.js`:

```js
/**
 * Display helpers for /subscription. Amounts arrive from Django in the
 * currency's minor unit (cents), exactly as Stripe stores them.
 */
export function formatAmount(cents, currency) {
  if (cents === null || cents === undefined) return null
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: (currency || 'usd').toUpperCase(),
  }).format(cents / 100)
}

/** Yearly price per month, in cents: 7188 -> 599. */
export function perMonth(yearCents) {
  return Math.round(yearCents / 12)
}

export function formatPlanDate(iso) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  // UTC so a period ending at midnight UTC doesn't show as the day before.
  return date.toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  })
}

/** The one-line status under the plan name, or null for free users. */
export function statusNote(sub) {
  if (!sub || sub.tier !== 'pro') return null
  const date = formatPlanDate(sub.current_period_end)

  if (!sub.status) {
    return { variant: 'info', text: 'Pro was added to your account by Fintank.' }
  }
  if (sub.status === 'past_due') {
    return { variant: 'warning', text: 'Your last payment failed. Update your card to keep Pro.' }
  }
  if (sub.cancel_at_period_end) {
    return { variant: 'secondary', text: `Your subscription is cancelled. Pro ends on ${date}.` }
  }
  return { variant: 'light', text: date ? `Renews on ${date}.` : 'Active.' }
}
```

- [ ] **Step 3: Run the harness and see it pass**

Run: `cp src/utils/subscriptionFormat.js $S/subfmt.mjs && node $S/subfmt.test.mjs`
Expected: every line starts with `ok`.

- [ ] **Step 4: Add the proxy route**

`src/pages/api/billing/[action].js`:

```js
import axios from 'axios'
import cookie from 'cookie'

/**
 * Proxies /api/billing/{subscription,checkout,portal} to Django with the
 * httpOnly `access` cookie as a Bearer token, like /api/backtester/[...path].
 * The Stripe webhook does not come through here; Stripe calls Django directly.
 * Nothing is logged: responses carry Stripe URLs tied to the user's session.
 */
const ROUTES = {
  subscription: 'GET',
  checkout: 'POST',
  portal: 'POST',
}

export default async function handler(req, res) {
  const method = ROUTES[req.query.action]
  if (!method) {
    return res.status(404).json({ detail: 'Not found.' })
  }
  if (req.method !== method) {
    res.setHeader('Allow', method)
    return res.status(405).json({ detail: `${req.method} is not supported here.` })
  }

  const { access } = cookie.parse(req.headers.cookie || '')
  if (!access) {
    return res.status(401).json({ detail: 'Your session has expired. Please log in again.' })
  }

  try {
    const response = await axios({
      method,
      url: `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/billing/${req.query.action}/`,
      data: method === 'POST' ? req.body || {} : undefined,
      headers: { Authorization: `Bearer ${access}`, 'Content-Type': 'application/json' },
      // 400/409/502/503 carry a `detail` the page shows, so pass them through.
      validateStatus: () => true,
    })
    return res.status(response.status).json(response.data)
  } catch (error) {
    return res.status(502).json({ detail: 'Billing is unreachable right now. Please try again.' })
  }
}
```

- [ ] **Step 5: Add the hook**

`src/hooks/useSubscription.js`:

```js
import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'

const POLL_EVERY_MS = 2000
const POLL_FOR_MS = 20000

/**
 * The signed-in user's plan. With `poll`, keeps refetching for up to 20 s until
 * the tier turns `pro` -- used right after Stripe Checkout, while the webhook
 * that upgrades the account is still on its way. `pollExpired` tells the page
 * to stop showing the spinner.
 */
export const useSubscription = ({ poll = false } = {}) => {
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pollExpired, setPollExpired] = useState(false)
  const startedAt = useRef(Date.now())

  const reload = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/billing/subscription')
      setSubscription(data)
      setError(null)
      return data
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load your subscription.')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    if (!poll || subscription?.tier === 'pro' || pollExpired) return undefined
    const timer = setTimeout(async () => {
      const data = await reload()
      if (data?.tier !== 'pro' && Date.now() - startedAt.current >= POLL_FOR_MS) {
        setPollExpired(true)
      }
    }, POLL_EVERY_MS)
    return () => clearTimeout(timer)
  }, [poll, subscription, pollExpired, reload])

  return { subscription, loading, error, pollExpired, reload }
}

export default useSubscription
```

- [ ] **Step 6: Add the page**

`src/pages/subscription.js` (LF endings — new file):

```js
import React, { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/router"
import {
  Alert,
  Badge,
  Breadcrumb,
  Button,
  ButtonGroup,
  Card,
  Col,
  Container,
  Row,
} from "react-bootstrap"
import axios from "axios"
import useProfileUser from "@componentsLegacy/Profile/useProfileUser"
import useSubscription from "@hooks/useSubscription"
import {
  formatAmount,
  perMonth,
  statusNote,
} from "@utils/subscriptionFormat"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Subscription",
    },
  }
}

const PRO_FEATURES = ["Unlimited portfolio backtests"]

const Spinner = () => (
  <div className="text-center py-5">
    <div className="spinner-border text-primary" role="status">
      <span className="visually-hidden">Loading...</span>
    </div>
  </div>
)

const Subscription = () => {
  const router = useRouter()
  const { user, loading: userLoading } = useProfileUser()
  const checkout = router.query.checkout
  const { subscription, loading, error, pollExpired } = useSubscription({
    poll: checkout === "success",
  })
  const [interval, setInterval] = useState("year")
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    if (!userLoading && !user) router.replace("/login")
  }, [userLoading, user, router])

  // Sends the browser to a Stripe-hosted page (checkout or portal).
  const goToStripe = async (action, body) => {
    setBusy(true)
    setActionError(null)
    try {
      const { data } = await axios.post(`/api/billing/${action}`, body)
      window.location.assign(data.url)
    } catch (err) {
      setActionError(err.response?.data?.detail || "Something went wrong. Please try again.")
      setBusy(false)
    }
  }

  const isPro = subscription?.tier === "pro"
  const plans = subscription?.plans
  const note = statusNote(subscription)
  const confirming = checkout === "success" && !isPro && !pollExpired

  return (
    <section className="account-page py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-start" }}>
          <Breadcrumb.Item linkAs={Link} href="/">
            Home
          </Breadcrumb.Item>
          <Breadcrumb.Item linkAs={Link} href="/user-account">
            Account
          </Breadcrumb.Item>
          <Breadcrumb.Item active>Subscription</Breadcrumb.Item>
        </Breadcrumb>

        <h1 className="hero-heading mb-0">Subscription</h1>
        <p className="text-muted mb-5">Your plan, billing and renewal.</p>

        <Row>
          <Col lg="7">
            {checkout === "cancelled" && (
              <Alert variant="secondary">Checkout cancelled. You have not been charged.</Alert>
            )}
            {checkout === "success" && pollExpired && !isPro && (
              <Alert variant="info">
                Your payment went through and your upgrade is still processing. Refresh this
                page in a minute.
              </Alert>
            )}
            {(error || actionError) && <Alert variant="danger">{actionError || error}</Alert>}

            {userLoading || loading || confirming ? (
              <>
                <Spinner />
                {confirming && <p className="text-center text-muted">Confirming your payment…</p>}
              </>
            ) : subscription && isPro ? (
              <Card className="border-0 shadow">
                <Card.Body className="p-4">
                  <div className="d-flex align-items-center mb-3">
                    <h3 className="mb-0 me-3">Pro</h3>
                    {subscription.interval && (
                      <Badge bg="primary">
                        {subscription.interval === "year" ? "Yearly" : "Monthly"}
                      </Badge>
                    )}
                  </div>
                  {note && <Alert variant={note.variant}>{note.text}</Alert>}
                  <ul className="mb-4">
                    {PRO_FEATURES.map((feature) => <li key={feature}>{feature}</li>)}
                  </ul>
                  {subscription.has_billing_account && (
                    <>
                      <Button variant="primary" disabled={busy} onClick={() => goToStripe("portal")}>
                        {busy ? "Opening…" : "Manage subscription"}
                      </Button>
                      <p className="text-sm text-muted mt-3 mb-0">
                        Switch between monthly and yearly, cancel, update your card or download
                        invoices on Stripe&apos;s secure billing page.
                      </p>
                    </>
                  )}
                </Card.Body>
              </Card>
            ) : subscription ? (
              <Card className="border-0 shadow">
                <Card.Body className="p-4">
                  <p className="text-muted mb-1">You are on the Free plan.</p>
                  <h3 className="mb-3">Upgrade to Pro</h3>
                  <ul className="mb-4">
                    {PRO_FEATURES.map((feature) => <li key={feature}>{feature}</li>)}
                  </ul>
                  {plans ? (
                    <>
                      <ButtonGroup className="mb-3" aria-label="Billing interval">
                        <Button
                          variant={interval === "month" ? "primary" : "outline-primary"}
                          onClick={() => setInterval("month")}
                        >
                          Monthly
                        </Button>
                        <Button
                          variant={interval === "year" ? "primary" : "outline-primary"}
                          onClick={() => setInterval("year")}
                        >
                          Yearly
                        </Button>
                      </ButtonGroup>
                      <p className="h4 mb-1">
                        {interval === "year"
                          ? `${formatAmount(perMonth(plans.year.amount), plans.year.currency)}/mo`
                          : `${formatAmount(plans.month.amount, plans.month.currency)}/mo`}
                      </p>
                      <p className="text-sm text-muted mb-4">
                        {interval === "year"
                          ? `Billed ${formatAmount(plans.year.amount, plans.year.currency)} yearly.`
                          : "Billed monthly."}{" "}
                        Cancel any time.
                      </p>
                      <Button
                        variant="primary"
                        disabled={busy}
                        onClick={() => goToStripe("checkout", { interval })}
                      >
                        {busy ? "Opening checkout…" : "Upgrade to Pro"}
                      </Button>
                    </>
                  ) : (
                    <p className="text-muted mb-0">
                      Upgrades are unavailable right now. Please try again later.
                    </p>
                  )}
                </Card.Body>
              </Card>
            ) : null}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default Subscription
```

Note: the local `interval` state name shadows `window.setInterval` inside this component only; that is intentional and harmless here, but if the linter flags `no-shadow` rename both to `billingInterval` / `setBillingInterval`.

- [ ] **Step 7: Add the account card**

Check endings first: `file src/data/user-account.json`. In `src/data/user-account.json`, after the "Login & security" card object add (keep the file's existing line endings):

```json
        {
            "title": "Subscription",
            "link": "/subscription",
            "icon": "pay-by-card-1",
            "content": "See your plan, upgrade to Pro, or manage and cancel your subscription"
        },
```

- [ ] **Step 8: Verify**

Run from `fintank/`:

```bash
node -e "JSON.parse(require('fs').readFileSync('src/data/user-account.json','utf8'))" && echo json-ok
npx eslint src/pages/subscription.js "src/pages/api/billing/[action].js" src/hooks/useSubscription.js src/utils/subscriptionFormat.js
file src/data/user-account.json
```

Expected: `json-ok`; no ESLint errors (warnings that already exist across the repo are fine); line endings unchanged from before the edit. Do **not** run `npm run build` — it always fails on the missing `anchor/target/idl/counter.json` (unrelated).

---

### Task 6: Final check and hand-off

- [ ] **Step 1: Full backend run**

Run: `cd fintank/backend && ../../.venv/bin/python manage.py test users backtester billing analyzer news`
Expected: all pass.

- [ ] **Step 2: Spec touch-up**

In the spec's "Supporting files" bullet, replace the three proxy filenames with `src/pages/api/billing/[action].js` (one route, three allowed actions).

- [ ] **Step 3: Report to Franc** what to do to try it (do not run any of it):

1. Stripe dashboard (test mode): product "Fintank Pro", prices $9.99/month and $71.88/year; Customer Portal: cancellation at period end, switching between the two prices, payment-method updates, invoice history.
2. `backend/.env`: `STRIPE_SECRET_KEY` (test key), `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY`, `FRONTEND_URL=http://localhost:8020`, `STRIPE_WEBHOOK_SECRET` (printed by step 3).
3. `stripe listen --forward-to localhost:8000/api/billing/webhook/`
4. `python manage.py migrate`, restart Django, `npm run dev`.
5. Test card `4242 4242 4242 4242`, any future date, any CVC.
6. Root `uv sync` would drop `stripe` from `.venv` unless it is also added to the root `pyproject.toml`.
