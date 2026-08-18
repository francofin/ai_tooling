"""Watchlist API.

The frontend's authContext has called these three routes since before they
existed -- /addtowatchlist/, /deletefromwatchlist/ and /stockonwatchlist/verify/
all 404'd, so every "Add to Watchlist" button in the app was inert. These tests
pin the response shapes that authContext.js already expects.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from stockuploader.models import ProfileStock, Stock

User = get_user_model()


def _user(email='watcher@example.com'):
    # This project's manager requires first/last name (users/managers.py).
    return User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')


def _client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


class WatchlistAuthenticationTests(TestCase):
    def test_anonymous_requests_are_rejected_everywhere(self):
        client = _client()
        for method, path in [
            ('post', '/api/addtowatchlist/AAPL/'),
            ('post', '/api/deletefromwatchlist/AAPL/'),
            ('get', '/api/stockonwatchlist/AAPL/verify/'),
        ]:
            with self.subTest(path=path):
                self.assertIn(getattr(client, method)(path).status_code, (401, 403))


class WatchlistTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.client = _client(self.user)
        self.stock = Stock.objects.create(symbol='RQP.TO', name='RBC Target 2027', is_etf=True)

    def test_add_creates_the_row_and_returns_the_shape_authcontext_expects(self):
        response = self.client.post('/api/addtowatchlist/RQP.TO/')
        self.assertEqual(response.status_code, 200)
        # authContext.js gates on `res.data.added === true` -- strictly true.
        self.assertIs(response.json()['added'], True)
        self.assertTrue(ProfileStock.objects.filter(user=self.user, stock=self.stock).exists())

    def test_adding_twice_does_not_duplicate_the_row(self):
        self.client.post('/api/addtowatchlist/RQP.TO/')
        self.client.post('/api/addtowatchlist/RQP.TO/')
        self.assertEqual(ProfileStock.objects.filter(user=self.user, stock=self.stock).count(), 1)

    def test_verify_reports_false_then_true(self):
        self.assertIs(self.client.get('/api/stockonwatchlist/RQP.TO/verify/').json(), False)
        self.client.post('/api/addtowatchlist/RQP.TO/')
        self.assertIs(self.client.get('/api/stockonwatchlist/RQP.TO/verify/').json(), True)

    def test_delete_removes_the_row(self):
        self.client.post('/api/addtowatchlist/RQP.TO/')
        response = self.client.post('/api/deletefromwatchlist/RQP.TO/')
        self.assertEqual(response.status_code, 200)
        # Same quirk: removeFromWatchlist also gates on `added === true`.
        self.assertIs(response.json()['added'], True)
        self.assertFalse(ProfileStock.objects.filter(user=self.user, stock=self.stock).exists())

    def test_deleting_something_absent_is_not_an_error(self):
        self.assertEqual(self.client.post('/api/deletefromwatchlist/RQP.TO/').status_code, 200)

    def test_dotted_and_lowercase_tickers_resolve(self):
        """RQP.TO is the case that started this -- a dot in the URL segment."""
        for ticker in ('RQP.TO', 'rqp.to', 'Rqp.To'):
            with self.subTest(ticker=ticker):
                self.assertEqual(self.client.post(f'/api/addtowatchlist/{ticker}/').status_code, 200)
        self.assertEqual(ProfileStock.objects.filter(user=self.user).count(), 1)

    def test_unknown_symbol_is_a_404_not_a_500(self):
        response = self.client.post('/api/addtowatchlist/NOTAREALSYM/')
        self.assertEqual(response.status_code, 404)
        self.assertIn('detail', response.json())

    def test_one_users_watchlist_is_invisible_to_another(self):
        self.client.post('/api/addtowatchlist/RQP.TO/')
        other = _client(_user('someone.else@example.com'))
        self.assertIs(other.get('/api/stockonwatchlist/RQP.TO/verify/').json(), False)
        # And removing it as the other user must not touch the owner's row.
        other.post('/api/deletefromwatchlist/RQP.TO/')
        self.assertTrue(ProfileStock.objects.filter(user=self.user, stock=self.stock).exists())
