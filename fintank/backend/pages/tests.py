from django.test import TestCase


class DashboardAccessTests(TestCase):

    def test_an_anonymous_visitor_is_redirected_to_the_landing_page(self):
        response = self.client.get('/dashboard/')
        self.assertRedirects(response, '/?next=/dashboard/', fetch_redirect_response=False)
