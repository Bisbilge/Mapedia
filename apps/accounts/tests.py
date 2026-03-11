from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import UserProfile


class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/auth/register/'

    def test_register_success(self):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_register_creates_user_profile(self):
        data = {
            'username': 'profileuser',
            'email': 'profile@example.com',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }
        self.client.post(self.url, data)
        user = User.objects.get(username='profileuser')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, UserProfile)

    def test_register_password_mismatch(self):
        data = {
            'username': 'baduser',
            'email': 'bad@example.com',
            'password': 'StrongPass123!',
            'password2': 'WrongPass123!',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        User.objects.create_user(username='existing', password='pass123')
        data = {
            'username': 'existing',
            'email': 'new@example.com',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_fields(self):
        response = self.client.post(self.url, {'username': 'incomplete'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/auth/login/'
        self.user = User.objects.create_user(
            username='loginuser',
            password='TestPass123!'
        )

    def test_login_success(self):
        response = self.client.post(self.url, {
            'username': 'loginuser',
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'username': 'loginuser',
            'password': 'WrongPass!'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        response = self.client.post(self.url, {
            'username': 'ghost',
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenRefreshTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='refreshuser',
            password='TestPass123!'
        )

    def _get_tokens(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'refreshuser',
            'password': 'TestPass123!'
        })
        return response.data

    def test_token_refresh_success(self):
        tokens = self._get_tokens()
        response = self.client.post('/api/v1/auth/refresh/', {
            'refresh': tokens['refresh']
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_token_refresh_invalid(self):
        response = self.client.post('/api/v1/auth/refresh/', {
            'refresh': 'notavalidtoken'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='profuser',
            email='prof@example.com',
            password='TestPass123!'
        )

    def _authenticate(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'profuser',
            'password': 'TestPass123!'
        })
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_get_profile_authenticated(self):
        self._authenticate()
        response = self.client.get('/api/v1/auth/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'profuser')

    def test_get_profile_unauthenticated(self):
        response = self.client.get('/api/v1/auth/profile/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_profile_bio(self):
        self._authenticate()
        response = self.client.patch('/api/v1/auth/profile/', {'bio': 'Hello world'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.bio, 'Hello world')


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='modeluser', password='pass')

    def test_profile_auto_created(self):
        self.assertIsNotNone(self.user.profile)

    def test_profile_default_role(self):
        self.assertEqual(self.user.profile.role, 'user')

    def test_is_moderator_property(self):
        profile = self.user.profile
        profile.role = 'moderator'
        profile.save()
        self.assertTrue(profile.is_moderator)

    def test_is_admin_property(self):
        profile = self.user.profile
        profile.role = 'admin'
        profile.save()
        self.assertTrue(profile.is_admin)
        self.assertTrue(profile.is_moderator)

    def test_is_trusted_default_false(self):
        self.assertFalse(self.user.profile.is_trusted)
