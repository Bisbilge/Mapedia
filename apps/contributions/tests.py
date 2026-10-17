from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from apps.venues.models import Venue
from apps.categories.models import Category, FieldDefinition
from apps.contributions.models import Contribution


# ── helpers ──────────────────────────────────────────────────────────────────

def make_user(username='u', password='pass123', is_trusted=False):
    user = User.objects.create_user(username=username, password=password)
    if is_trusted:
        user.profile.is_trusted = True
        user.profile.save()
    return user


def make_category(owner=None, slug='cat', name='Category'):
    return Category.objects.create(name=name, slug=slug, owner=owner)


def make_venue(category, name='Venue', is_approved=True):
    return Venue.objects.create(
        name=name,
        latitude='41.015137',
        longitude='28.979530',
        city='Istanbul',
        country='Turkey',
        category=category,
        is_approved=is_approved,
    )


def get_token(client, user, password='pass123'):
    r = client.post('/api/v1/auth/login/', {
        'username': user.username, 'password': password
    })
    return r.data['access']


# ── New Venue Contribution ────────────────────────────────────────────────────

class CreateVenueContributionTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('contributor')
        self.owner = make_user('catowner')
        self.cat = make_category(owner=self.owner, slug='restrooms')

    def _auth(self, user):
        token = get_token(self.client, user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _payload(self, **kwargs):
        base = {
            'name': 'New Place',
            'latitude': '41.015137',
            'longitude': '28.979530',
            'city': 'Istanbul',
            'country': 'Turkey',
            'category': 'restrooms',
        }
        base.update(kwargs)
        return base

    def test_unauthenticated_cannot_contribute(self):
        response = self.client.post('/api/v1/contributions/venue/', self._payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create_contribution(self):
        self._auth(self.user)
        response = self.client.post('/api/v1/contributions/venue/', self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Contribution.objects.count(), 1)
        c = Contribution.objects.first()
        self.assertEqual(c.status, 'pending')
        self.assertEqual(c.contribution_type, 'add_venue')

    def test_contribution_not_auto_approved_for_regular_user(self):
        self._auth(self.user)
        self.client.post('/api/v1/contributions/venue/', self._payload())
        c = Contribution.objects.first()
        self.assertEqual(c.status, 'pending')
        # No venue should be created yet
        self.assertEqual(Venue.objects.count(), 0)

    def test_trusted_user_contribution_auto_approved(self):
        trusted = make_user('trusted', is_trusted=True)
        self._auth(trusted)
        self.client.post('/api/v1/contributions/venue/', self._payload())
        c = Contribution.objects.first()
        self.assertEqual(c.status, 'approved')
        self.assertEqual(Venue.objects.count(), 1)

    def test_missing_required_fields_returns_400(self):
        self._auth(self.user)
        response = self.client.post('/api/v1/contributions/venue/', {'name': 'Incomplete'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_category_returns_400(self):
        self._auth(self.user)
        response = self.client.post('/api/v1/contributions/venue/', self._payload(category='nonexistent'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ── Approve / Reject ──────────────────────────────────────────────────────────

class ContributionModerationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('owner')
        self.mod = make_user('mod')
        self.contributor = make_user('contrib')
        self.cat = make_category(owner=self.owner, slug='mcat')
        self.cat.moderators.add(self.mod)

    def _auth(self, user):
        token = get_token(self.client, user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _make_contribution(self):
        return Contribution.objects.create(
            contributor=self.contributor.profile,
            contribution_type='add_venue',
            payload={
                'name': 'Test Venue',
                'latitude': '41.0',
                'longitude': '29.0',
                'city': 'Istanbul',
                'country': 'Turkey',
                'category': 'mcat',
                'field_values': {},
            }
        )

    def test_owner_can_approve(self):
        c = self._make_contribution()
        self._auth(self.owner)
        response = self.client.post(f'/api/v1/contributions/{c.id}/approve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        c.refresh_from_db()
        self.assertEqual(c.status, 'approved')
        self.assertEqual(Venue.objects.count(), 1)

    def test_moderator_can_approve(self):
        c = self._make_contribution()
        self._auth(self.mod)
        response = self.client.post(f'/api/v1/contributions/{c.id}/approve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_approve(self):
        other = make_user('other')
        c = self._make_contribution()
        self._auth(other)
        response = self.client.post(f'/api/v1/contributions/{c.id}/approve/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_reject(self):
        c = self._make_contribution()
        self._auth(self.owner)
        response = self.client.post(f'/api/v1/contributions/{c.id}/reject/', {
            'note': 'Duplicate entry.'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        c.refresh_from_db()
        self.assertEqual(c.status, 'rejected')
        self.assertEqual(c.moderation_note, 'Duplicate entry.')

    def test_approve_nonexistent_contribution_returns_404(self):
        self._auth(self.owner)
        response = self.client.post('/api/v1/contributions/99999/approve/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_already_approved_returns_404(self):
        """Already-approved contributions should not be re-processed."""
        c = self._make_contribution()
        c.status = 'approved'
        c.save()
        self._auth(self.owner)
        response = self.client.post(f'/api/v1/contributions/{c.id}/approve/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_increments_contribution_count(self):
        c = self._make_contribution()
        initial_count = self.contributor.profile.contribution_count
        self._auth(self.owner)
        self.client.post(f'/api/v1/contributions/{c.id}/approve/')
        self.contributor.profile.refresh_from_db()
        self.assertEqual(self.contributor.profile.contribution_count, initial_count + 1)


# ── Edit Venue ────────────────────────────────────────────────────────────────

class EditVenueContributionTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('editowner')
        self.regular = make_user('editregular')
        self.cat = make_category(owner=self.owner, slug='editcat')
        self.venue = make_venue(self.cat)

    def _auth(self, user):
        token = get_token(self.client, user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_moderator_can_create_edit_contribution(self):
        self._auth(self.owner)
        response = self.client.post(
            f'/api/v1/contributions/venue/{self.venue.id}/edit/',
            {'name': 'Updated Name', 'city': 'Ankara'}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_regular_user_cannot_create_edit_contribution(self):
        self._auth(self.regular)
        response = self.client.post(
            f'/api/v1/contributions/venue/{self.venue.id}/edit/',
            {'name': 'Hacked Name'}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_edit_contribution_auto_applied_for_trusted(self):
        self.owner.profile.is_trusted = True
        self.owner.profile.save()
        self._auth(self.owner)
        self.client.post(
            f'/api/v1/contributions/venue/{self.venue.id}/edit/',
            {'name': 'Trusted Edit', 'city': 'Bursa'}
        )
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.name, 'Trusted Edit')
        self.assertEqual(self.venue.city, 'Bursa')


# ── Pending List ──────────────────────────────────────────────────────────────

class PendingContributionsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('pendingowner')
        self.contributor = make_user('pendingcontrib')
        self.cat = make_category(owner=self.owner, slug='pendingcat')

    def _auth(self, user):
        token = get_token(self.client, user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _make_contribution(self):
        return Contribution.objects.create(
            contributor=self.contributor.profile,
            contribution_type='add_venue',
            payload={
                'name': 'Pending Venue',
                'category': 'pendingcat',
                'field_values': {},
            }
        )

    def test_owner_sees_pending_categories(self):
        self._make_contribution()
        self._auth(self.owner)
        response = self.client.get('/api/v1/contributions/pending/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [c['slug'] for c in response.data]
        self.assertIn('pendingcat', slugs)

    def test_owner_can_filter_by_category(self):
        self._make_contribution()
        self._auth(self.owner)
        response = self.client.get('/api/v1/contributions/pending/?category=pendingcat')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_regular_user_sees_empty_list(self):
        self._make_contribution()
        self._auth(self.contributor)
        response = self.client.get('/api/v1/contributions/pending/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_unauthenticated_cannot_access_pending(self):
        response = self.client.get('/api/v1/contributions/pending/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ── VenueReport ───────────────────────────────────────────────────────────────

class VenueReportTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('reportowner')
        self.cat = make_category(owner=self.owner, slug='reportcat')
        self.venue = make_venue(self.cat, name='Reportable Venue')

    def test_anyone_can_submit_report(self):
        response = self.client.post('/api/v1/reports/', {
            'venue': self.venue.id,
            'reason': 'closed',
            'description': 'This place is closed.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_reason_returns_400(self):
        response = self.client.post('/api/v1/reports/', {
            'venue': self.venue.id,
            'reason': 'bad_reason',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
