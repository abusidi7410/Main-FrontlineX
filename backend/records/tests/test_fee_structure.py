"""Fee structure read/write behaviour (Phase 1 gap fix).

`updateFeeStructure` existed in the service layer and `FeeStructureView` existed
on the backend, but no UI ever called the write path, so an admin could not
configure what to bill. These tests pin the endpoint the editor depends on.
"""
from records.models import FeeStructure

from .test_security import SecurityTestBase

ITEMS = [
    {'label': 'Tuition', 'amount': 50000.0, 'className': '*'},
    {'label': 'Development levy', 'amount': 5000.0, 'className': 'JSS 1'},
]


class FeeStructureTests(SecurityTestBase):
    def url_path(self):
        return self.url('/fees/structure/')

    def test_read_returns_the_schools_structure(self):
        self.school.fee_structure = ITEMS
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.admin)
        r = self.client.get(self.url_path())
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['items'], ITEMS)

    def test_accountant_can_save(self):
        self.auth(self.accountant)
        r = self.client.put(self.url_path(), {'items': ITEMS}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.school.refresh_from_db()
        self.assertEqual(self.school.fee_structure, ITEMS)

    def test_school_admin_can_save(self):
        self.auth(self.admin)
        r = self.client.put(self.url_path(), {'items': ITEMS}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_teacher_is_denied(self):
        self.auth(self.teacher)
        r = self.client.put(self.url_path(), {'items': ITEMS}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_unauthenticated_is_denied(self):
        self.client.force_authenticate(user=None)
        r = self.client.put(self.url_path(), {'items': ITEMS}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_empty_structure_is_allowed(self):
        """Clearing the fee list is legitimate, so an empty list must save."""
        self.school.fee_structure = ITEMS
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.accountant)
        r = self.client.put(self.url_path(), {'items': []}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.school.refresh_from_db()
        self.assertEqual(self.school.fee_structure, [])

    def test_blank_label_is_rejected(self):
        self.auth(self.accountant)
        r = self.client.put(
            self.url_path(), {'items': [{'label': '  ', 'amount': 100, 'className': '*'}]},
            format='json',
        )
        self.assertEqual(r.status_code, 400)
        # The API wrapper flattens DRF's dict errors into `fieldErrors`.
        self.assertIn('items', r.json()['fieldErrors'])

    def test_non_positive_amount_is_rejected(self):
        self.auth(self.accountant)
        r = self.client.put(
            self.url_path(), {'items': [{'label': 'Tuition', 'amount': 0, 'className': '*'}]},
            format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_non_numeric_amount_is_rejected(self):
        self.auth(self.accountant)
        r = self.client.put(
            self.url_path(), {'items': [{'label': 'Tuition', 'amount': 'free', 'className': '*'}]},
            format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_items_must_be_a_list(self):
        self.auth(self.accountant)
        r = self.client.put(self.url_path(), {'items': {'label': 'x'}}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_structure_is_per_school(self):
        """One school's fees must never leak into another's."""
        self.school.fee_structure = ITEMS
        self.school.save(update_fields=['fee_structure'])
        self.auth(self.other_admin)
        r = self.client.get(self.url_path())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['items'], [])
        self.school.refresh_from_db()
        self.assertEqual(self.school.fee_structure, ITEMS)

    def test_model_default_is_empty_not_null(self):
        self.assertIsInstance(self.school.fee_structure, list)
        self.assertTrue(hasattr(FeeStructure, 'Scope'))
