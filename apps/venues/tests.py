from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from apps.venues.models import Venue
from apps.categories.models import Category, FieldDefinition, FieldValue


def make_category(owner=None, slug='test-cat', name='Test Category'):
    return Category.objects.create(name=name, slug=slug, owner=owner)


def make_venue(category=None, name='Test Venue', is_approved=True):
    return Venue.objects.create(
        name=name,
        latitude='41.015137',
        longitude='28.979530',
        city='Istanbul',
        country='Turkey',
        category=category,
        is_approved=is_approved,
    )


class VenueListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cat = make_category()
        self.venue1 = make_venue(self.cat, name='Venue One')
        self.venue2 = make_venue(self.cat, name='Venue Two')
        # Unapproved venue — should not appear in list
        self.venue3 = make_venue(self.cat, name='Hidden Venue', is_approved=False)

    def test_list_returns_only_approved(self):
        response = self.client.get('/api/v1/venues/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [v['name'] for v in response.data['results']]
        self.assertIn('Venue One', names)
        self.assertIn('Venue Two', names)
        self.assertNotIn('Hidden Venue', names)

    def test_filter_by_category(self):
        other_cat = make_category(slug='other-cat', name='Other')
        make_venue(other_cat, name='Other Venue')
        response = self.client.get('/api/v1/venues/?category=test-cat')
        names = [v['name'] for v in response.data['results']]
        self.assertIn('Venue One', names)
        self.assertNotIn('Other Venue', names)

    def test_filter_by_city(self):
        make_venue(self.cat, name='Ankara Venue')
        # Override city
        v = Venue.objects.get(name='Ankara Venue')
        v.city = 'Ankara'
        v.save()
        response = self.client.get('/api/v1/venues/?city=ankara')
        names = [v['name'] for v in response.data['results']]
        self.assertIn('Ankara Venue', names)
        self.assertNotIn('Venue One', names)

    def test_search_by_name(self):
        response = self.client.get('/api/v1/venues/?search=Venue One')
        names = [v['name'] for v in response.data['results']]
        self.assertIn('Venue One', names)

    def test_list_unauthenticated_allowed(self):
        response = self.client.get('/api/v1/venues/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class VenueDetailViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='owner', password='pass123')
        self.regular = User.objects.create_user(username='regular', password='pass123')
        self.cat = make_category(owner=self.owner)
        self.venue = make_venue(self.cat)

    def _auth(self, user):
        r = self.client.post('/api/v1/auth/login/', {
            'username': user.username, 'password': 'pass123'
        })
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def test_detail_returns_venue(self):
        response = self.client.get(f'/api/v1/venues/{self.venue.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Venue')

    def test_detail_can_edit_false_for_regular_user(self):
        self._auth(self.regular)
        response = self.client.get(f'/api/v1/venues/{self.venue.id}/')
        self.assertFalse(response.data['can_edit'])

    def test_detail_can_edit_true_for_owner(self):
        self._auth(self.owner)
        response = self.client.get(f'/api/v1/venues/{self.venue.id}/')
        self.assertTrue(response.data['can_edit'])

    def test_detail_can_edit_false_unauthenticated(self):
        response = self.client.get(f'/api/v1/venues/{self.venue.id}/')
        self.assertFalse(response.data['can_edit'])

    def test_detail_unapproved_not_found(self):
        unapproved = make_venue(self.cat, name='Unapproved', is_approved=False)
        response = self.client.get(f'/api/v1/venues/{unapproved.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class VenueModelTest(TestCase):
    def test_slug_auto_generated(self):
        venue = Venue.objects.create(name='My Cool Venue')
        self.assertEqual(venue.slug, 'my-cool-venue')

    def test_slug_unique_on_duplicate_name(self):
        v1 = Venue.objects.create(name='Duplicate')
        v2 = Venue.objects.create(name='Duplicate')
        self.assertNotEqual(v1.slug, v2.slug)
        self.assertEqual(v2.slug, 'duplicate-1')

    def test_slug_not_overwritten_on_save(self):
        venue = Venue.objects.create(name='Original Name')
        original_slug = venue.slug
        venue.name = 'Changed Name'
        venue.save()
        self.assertEqual(venue.slug, original_slug)
