from django.test import TestCase


class DashboardAccessTests(TestCase):

    def test_an_anonymous_visitor_is_redirected_to_the_landing_page(self):
        response = self.client.get('/dashboard/', follow=True)
        self.assertEqual(response.redirect_chain, [('/?next=/dashboard/', 302)])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'action="/login/"')
