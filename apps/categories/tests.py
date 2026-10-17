from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from apps.categories.models import Category, FieldDefinition


def make_user(username='user', password='pass123'):
    return User.objects.create_user(username=username, password=password)


def make_category(owner=None, slug='cat', name='Category'):
    return Category.objects.create(name=name, slug=slug, owner=owner)


class CategoryListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        make_category(slug='cat1', name='Cat One')
        make_category(slug='cat2', name='Cat Two')
        c = make_category(slug='inactive', name='Inactive')
        c.is_active = False
        c.save()

    def test_list_returns_active_only(self):
        response = self.client.get('/api/v1/categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [c['name'] for c in response.data['results']]
        self.assertIn('Cat One', names)
        self.assertIn('Cat Two', names)
        self.assertNotIn('Inactive', names)

    def test_list_unauthenticated_allowed(self):
        response = self.client.get('/api/v1/categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_by_name(self):
        response = self.client.get('/api/v1/categories/?search=Cat One')
        names = [c['name'] for c in response.data['results']]
        self.assertIn('Cat One', names)


class CategoryDetailViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('owner')
        self.cat = make_category(owner=self.owner, slug='detail-cat')
        # Add a field definition
        FieldDefinition.objects.create(
            category=self.cat,
            name='toilet_code',
            label='Toilet Code',
            field_type='string',
        )

    def test_detail_by_slug(self):
        response = self.client.get('/api/v1/categories/detail-cat/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Category')

    def test_detail_includes_field_definitions(self):
        response = self.client.get('/api/v1/categories/detail-cat/')
        self.assertIn('field_definitions', response.data)

    def test_detail_not_found(self):
        response = self.client.get('/api/v1/categories/nonexistent/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CategoryModeratorsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user('catowner')
        self.other = make_user('other')
        self.mod = make_user('moduser')
        self.cat = make_category(owner=self.owner, slug='mod-cat')
        self.cat.moderators.add(self.mod)

    def _auth(self, user):
        r = self.client.post('/api/v1/auth/login/', {
            'username': user.username, 'password': 'pass123'
        })
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def test_owner_can_list_moderators(self):
        self._auth(self.owner)
        response = self.client.get('/api/v1/categories/mod-cat/moderators/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [m['username'] for m in response.data]
        self.assertIn('moduser', usernames)

    def test_non_owner_cannot_list_moderators(self):
        self._auth(self.other)
        response = self.client.get('/api/v1/categories/mod-cat/moderators/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_add_moderator(self):
        new_mod = make_user('newmod')
        self._auth(self.owner)
        response = self.client.post('/api/v1/categories/mod-cat/moderators/add/', {
            'user_id': new_mod.id
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(new_mod, self.cat.moderators.all())

    def test_owner_can_remove_moderator(self):
        self._auth(self.owner)
        response = self.client.post('/api/v1/categories/mod-cat/moderators/remove/', {
            'user_id': self.mod.id
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.mod, self.cat.moderators.all())

    def test_add_nonexistent_user_returns_404(self):
        self._auth(self.owner)
        response = self.client.post('/api/v1/categories/mod-cat/moderators/add/', {
            'user_id': 99999
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CategoryCanModerateTest(TestCase):
    def setUp(self):
        self.owner = make_user('co')
        self.mod = make_user('cm')
        self.regular = make_user('cr')
        self.superuser = User.objects.create_superuser('super', password='super123')
        self.cat = make_category(owner=self.owner, slug='perm-cat')
        self.cat.moderators.add(self.mod)

    def test_owner_can_moderate(self):
        self.assertTrue(self.cat.can_moderate(self.owner))

    def test_moderator_can_moderate(self):
        self.assertTrue(self.cat.can_moderate(self.mod))

    def test_regular_cannot_moderate(self):
        self.assertFalse(self.cat.can_moderate(self.regular))

    def test_superuser_can_moderate(self):
        self.assertTrue(self.cat.can_moderate(self.superuser))
