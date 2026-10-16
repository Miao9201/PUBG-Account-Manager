"""Requested ban policy and confirmed-password-only automatic deletion."""
import queue
import io
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_ban_manager as main
import steam_login


def player(**changes):
    value = {'VACBanned': False, 'NumberOfVACBans': 0, 'NumberOfGameBans': 0,
             'CommunityBanned': False, 'EconomyBan': 'none'}
    value.update(changes)
    return value


def auth_error(code):
    return steam_login._auth_error({'response': {'error': {'eresult': code}}}, 200)


class PubgStatusTest(unittest.TestCase):
    def test_global_api_failure_preserves_account_results_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                first = store.upsert_account('first', '76561198000000001', '', 'test')
                store.save_result(first, player(NumberOfGameBans=1))
                store.upsert_account('later', '76561198000000002', '', 'test')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                app.query_cancel_event = threading.Event()
                with patch.object(main, 'CONSERVATIVE_BATCH_SIZE', 1), \
                     patch.object(main, 'request_player_bans', side_effect=main.SteamApiFatalError('bad key')):
                    app._query_worker('test-key', None, 2, path)
                events = list(app.events.queue)
                self.assertEqual([payload for kind, payload in events if kind == 'result_batch'], [])
                self.assertEqual(store.connection.execute('SELECT status FROM accounts WHERE id=?', (first,)).fetchone()[0],
                                 '查询成功')
                self.assertEqual(events[-1][0], 'query_blocked')
                self.assertEqual(sum(kind in ('query_done', 'query_cancelled', 'query_blocked')
                                     for kind, _ in events), 1)
            finally:
                store.close()

    def test_cancelled_retry_wait_returns_without_sleeping(self):
        app = main.SteamBanApp.__new__(main.SteamBanApp)
        app.query_cancel_event = threading.Event()
        app.query_cancel_event.set()
        with patch.object(main.time, 'sleep') as sleep:
            self.assertFalse(app._wait_resolve_retry(2))
        sleep.assert_not_called()

    def test_query_cancellation_discards_inflight_response_without_marking_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                account_id = store.upsert_account('demo', '76561198000000001', '', 'test-password')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                app.query_cancel_event = threading.Event()
                def respond(*_args, **_kwargs):
                    app.query_cancel_event.set()
                    return {'76561198000000001': player()}
                with patch.object(main, 'request_player_bans', side_effect=respond):
                    app._query_worker('test-key', [account_id], 1, path)
                events = list(app.events.queue)
                self.assertIn(('query_cancelled', (0, 1)), events)
                self.assertNotIn('result_batch', [kind for kind, _ in events])
                self.assertNotIn('query_done', [kind for kind, _ in events])
                self.assertEqual(store.list_accounts_page(0, 1)[0][0]['status'], '未查询')
            finally:
                store.close()

    def test_query_cancel_during_password_check_never_deletes_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                key = store.upsert_account('demo', '76561198000000001', '', 'test-password')
                store.set_auto_delete_wrong_password(True)
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                app.query_cancel_event = threading.Event()
                def reject(*_args):
                    app.query_cancel_event.set()
                    raise auth_error(5)
                with patch.object(steam_login, 'resolve_steam_id', side_effect=reject), \
                     patch.object(main, 'request_player_bans') as request:
                    app._query_worker('test-key', [key], 1, path)
                request.assert_not_called()
                self.assertEqual(store.count_accounts(), 1)
                self.assertIn(('query_cancelled', (0, 1)), list(app.events.queue))
            finally:
                store.close()

    def test_failed_duplicate_edit_releases_database_for_other_writers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                first = store.upsert_account('first', '76561198000000001', '', 'first-password')
                second = store.upsert_account('second', '76561198000000002', '', 'second-password')
                with self.assertRaises(sqlite3.IntegrityError):
                    store.upsert_account('changed', '76561198000000002', '', 'changed', account_id=first)
                self.assertFalse(store.connection.in_transaction)
                other_writer = sqlite3.connect(path, timeout=0.1)
                try:
                    with other_writer:
                        other_writer.execute('UPDATE accounts SET note=? WHERE id=?', ('worker update', second))
                finally:
                    other_writer.close()
                self.assertEqual(store.account_password(first), 'first-password')
                self.assertEqual(store.account_objects([first])[0].account_name, 'first')
            finally:
                store.close()

    def test_keyboard_and_context_commands_cannot_edit_or_delete_during_tasks(self):
        for busy_flag in ('query_running', 'import_running', 'login_running'):
            with self.subTest(task=busy_flag):
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                for flag in ('query_running', 'import_running', 'login_running'):
                    setattr(app, flag, flag == busy_flag)
                app.root = MagicMock()
                app.store = MagicMock()
                app.store.account_objects.return_value = [main.Account(1, 'demo', '76561198000000001', '')]
                app._selected_ids = lambda: [1]
                app.checked_ids = {1}
                app.refresh_table = MagicMock()
                app.status_var = MagicMock()
                with patch.object(main, 'AccountDialog') as editor, \
                     patch.object(main.messagebox, 'askyesno', return_value=True):
                    editor.return_value.result = None
                    app.edit_selected()
                    app.delete_selected()
                    editor.assert_not_called()
                    app.store.delete_accounts.assert_not_called()
                    self.assertEqual(app.checked_ids, {1})

    def test_account_totals_count_each_banned_account_once_and_ignore_vac_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                self.assertEqual(store.account_totals(), (0, 0))
                cases = [player(NumberOfGameBans=3, CommunityBanned=True, EconomyBan='banned'),
                         player(CommunityBanned=True), player(EconomyBan='probation'),
                         player(VACBanned=True), player(EconomyBan='unknown'), player(), None, None]
                ids = []
                for index, payload in enumerate(cases):
                    account = store.upsert_account(f'demo_{index}', f'7656119800000000{index}', '', 'test')
                    ids.append(account)
                    if payload is not None:
                        store.save_result(account, payload)
                store.save_result(ids[-1], None, '查询失败')
                self.assertEqual(store.account_totals(), (8, 3))
                store.list_accounts_page(0, 1, 'safe')
                self.assertEqual(store.account_totals(), (8, 3))
                store.delete_accounts([ids[0]])
                self.assertEqual(store.account_totals(), (7, 2))
            finally:
                store.close()

    def test_only_non_vac_bans_are_combined(self):
        for payload, expected in (
            (player(VACBanned=True, NumberOfVACBans=3), '未封禁'),
            (player(NumberOfGameBans=1), 'PUBG封禁'),
            (player(CommunityBanned=True), 'PUBG封禁'),
            (player(EconomyBan='banned'), 'PUBG封禁'),
            (player(EconomyBan='probation'), 'PUBG封禁'),
            (player(EconomyBan='unknown'), '未知'),
            (player(), '未封禁'),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(main.pubg_assessment(payload), expected)

    def test_vac_only_is_not_in_risk_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                only_vac = store.upsert_account('vac_only', '76561198000000001', '', 'test')
                community = store.upsert_account('community', '76561198000000002', '', 'test')
                store.save_result(only_vac, player(VACBanned=True, NumberOfVACBans=1))
                store.save_result(community, player(CommunityBanned=True))
                rows, _ = store.list_accounts_page(0, 20, 'risk')
                self.assertEqual({row['id'] for row in rows}, {community})
                self.assertEqual(store.count_accounts('safe'), 1)
            finally:
                store.close()

    def test_only_official_invalid_password_code_is_destructive(self):
        self.assertTrue(hasattr(steam_login, 'SteamInvalidPasswordError'))
        self.assertIsInstance(auth_error(5), steam_login.SteamInvalidPasswordError)
        for code in (20, 63, 65, 84, 85, 88):
            with self.subTest(code=code):
                self.assertNotIsInstance(auth_error(code), steam_login.SteamInvalidPasswordError)

    def test_http_result_header_is_preserved_for_password_detection(self):
        class Response:
            headers = {'x-eresult': '5'}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"response": {}}'
        with patch.object(steam_login, 'urlopen', return_value=Response()):
            payload = steam_login._auth_json(object())
        self.assertIsInstance(steam_login._auth_error(payload, 200), steam_login.SteamInvalidPasswordError)

    def test_empty_http_error_body_uses_result_code_without_confusing_service_failure(self):
        key = {'response': {'publickey_mod': 'f' * 256, 'publickey_exp': '10001', 'timestamp': '1'}}
        for code in (5, 20):
            with self.subTest(code=code):
                error = HTTPError('https://api.steampowered.com/', 401, 'Unauthorized',
                                  {'x-eresult': str(code)}, io.BytesIO(b''))
                with patch.object(steam_login, '_auth_json', side_effect=[key, error]):
                    try:
                        steam_login.resolve_steam_id('demo', 'test-password')
                    except steam_login.SteamAuthError as rejection:
                        self.assertEqual(isinstance(rejection, steam_login.SteamInvalidPasswordError), code == 5)
                    else:
                        self.fail('The failed authentication must reject the credentials')

    def test_setting_persists_and_changed_password_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                self.assertFalse(store.auto_delete_wrong_password_enabled())
                store.set_auto_delete_wrong_password(True)
                key = store.upsert_account('changed', '76561198000000001', '', 'new-password')
                self.assertFalse(store.delete_wrong_password_account(key, 'old-password'))
                self.assertEqual(store.account_password(key), 'new-password')
                store.connection.execute('UPDATE accounts SET account_name=? WHERE id=?', ('renamed', key))
                store.connection.commit()
                self.assertFalse(store.delete_wrong_password_account(key, 'new-password', 'changed'))
                self.assertTrue(store.delete_wrong_password_account(key, 'new-password'))
                self.assertEqual(store.count_accounts(), 0)
            finally:
                store.close()

    def test_many_invalid_passwords_are_deleted_without_stopping_after_five(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                for index in range(1, 7):
                    store.upsert_account(f'bad_{index}', f'7656119800000000{index}', '', 'bad-password')
                store.set_auto_delete_wrong_password(True)
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                with patch.object(steam_login, 'resolve_steam_id', side_effect=auth_error(5)), \
                     patch.object(main, 'CONSERVATIVE_BATCH_SIZE', 2):
                    app._query_worker('unused-test-key', None, 6, path)
                self.assertEqual(store.count_accounts(), 0)
                events = list(app.events.queue)
                self.assertIn(('query_done', 6), events)
                self.assertEqual(sum(kind == 'invalid_password_deleted' for kind, _ in events), 6)
            finally:
                store.close()
            reopened = main.AccountStore(path)
            try:
                self.assertTrue(reopened.auto_delete_wrong_password_enabled())
            finally:
                reopened.close()

    def test_query_checks_known_ids_and_deletes_only_confirmed_bad_password(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                keys = [store.upsert_account(name, f'7656119800000000{index}', '', 'test-password')
                        for index, name in enumerate(('bad', 'service_down', 'guard', 'timeout', 'good'), 1)]
                store.set_auto_delete_wrong_password(True)
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()

                def resolve(account, _password):
                    if account == 'bad':
                        raise auth_error(5)
                    if account == 'service_down':
                        raise auth_error(20)
                    if account == 'guard':
                        raise auth_error(63)
                    if account == 'timeout':
                        raise steam_login.SteamAuthError('timed out')
                    return '76561198000000005'

                with patch.object(steam_login, 'resolve_steam_id', side_effect=resolve), \
                     patch.object(main, 'RESOLVE_ATTEMPTS', 1), patch.object(main.time, 'sleep'):
                    resolved, _, _, handled = app._resolve_batch_ids(store.account_objects(keys), 0, store, 0, 5)
                self.assertEqual(handled, 5)
                self.assertEqual({account.account_id for account in resolved}, set(keys[1:]))
                self.assertEqual(store.count_accounts(), 4)
                self.assertIsNone(store.connection.execute('SELECT id FROM accounts WHERE id=?', (keys[0],)).fetchone())
            finally:
                store.close()

    def test_login_validates_before_closing_steam_and_defers_deletion_to_ui(self):
        app = main.SteamBanApp.__new__(main.SteamBanApp)
        app.events = queue.Queue()
        with patch.object(steam_login, 'resolve_steam_id', side_effect=auth_error(5)), \
             patch.object(steam_login, 'shutdown_steam') as shutdown:
            app._steam_login_worker('steam.exe', 'bad', '76561198000000001', 'bad-password',
                                    7, None, threading.Event(), auto_delete_wrong_password=True)
        shutdown.assert_not_called()
        kind, payload = app.events.get_nowait()
        self.assertEqual(kind, 'steam_login_invalid_password')
        self.assertEqual(payload[0], 7)

    def test_cancel_during_password_check_never_closes_steam(self):
        for error in (None, steam_login.SteamAuthError('service unavailable')):
            with self.subTest(error=error):
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                cancellation = threading.Event()
                def resolve(*args):
                    cancellation.set()
                    if error:
                        raise error
                    return '76561198000000001'
                with patch.object(steam_login, 'resolve_steam_id', side_effect=resolve), \
                     patch.object(steam_login, 'shutdown_steam') as shutdown:
                    app._steam_login_worker('steam.exe', 'demo', '76561198000000001', 'test-password',
                                            7, None, cancellation, auto_delete_wrong_password=True)
                shutdown.assert_not_called()
                self.assertEqual(app.events.get_nowait()[0], 'steam_login_cancelled')


if __name__ == '__main__':
    unittest.main()
