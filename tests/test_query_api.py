"""Query regressions using disposable databases and mocked Steam responses only."""
import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_ban_manager as main
import steam_login

ID = '76561198000000001'
OTHER = '76561198000000002'


def player(steam_id=ID, **changes):
    return dict(SteamId=steam_id, CommunityBanned=False, NumberOfGameBans=0,
                EconomyBan='none', **changes)


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode('utf-8'))


def add_placeholder(store, name):
    with store.connection:
        store.connection.execute(store.UPSERT_SQL, (name, name, '', 'test', main.utc_now()))
    return store.connection.execute('SELECT id FROM accounts WHERE steam_id=?', (name,)).fetchone()[0]


class QueryApiTest(unittest.TestCase):
    def test_unqueried_filter_lists_and_exports_only_unqueried_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                pending = store.upsert_account('pending', ID, '', 'test')
                safe = store.upsert_account('safe', OTHER, '', 'test')
                failed = store.upsert_account('failed', '76561198000000003', '', 'test')
                cancelled = store.upsert_account('cancelled', '76561198000000004', '', 'test')
                cancelled_safe = store.upsert_account('cancelled_safe', '76561198000000005', '', 'test')
                cancelled_banned = store.upsert_account('cancelled_banned', '76561198000000006', '', 'test')
                store.save_result(safe, player(OTHER))
                store.save_result(failed, None, 'test failure')
                store.save_result(cancelled_safe, player('76561198000000005'))
                store.save_result(cancelled_banned, dict(player('76561198000000006'), NumberOfGameBans=1))
                with store.connection:
                    store.connection.executemany("UPDATE accounts SET status='已取消' WHERE id=?",
                                                 [(cancelled,), (cancelled_safe,), (cancelled_banned,)])
                rows, total = store.list_accounts_page(0, 10, 'unqueried')
                self.assertEqual(total, 2)
                self.assertEqual([row['id'] for row in rows], [pending, cancelled])
                self.assertEqual(store.count_accounts('unqueried'), 2)
                self.assertEqual([row[0] for row in store.export_account_rows(None, 'unqueried')], ['cancelled', 'pending'])
                store.save_result(pending, player(ID))
                self.assertEqual(store.count_accounts('unqueried'), 1)
                store.save_result(cancelled, player('76561198000000004'))
                self.assertEqual(store.count_accounts('unqueried'), 0)
            finally:
                store.close()

    def test_display_order_is_first_imported_first_even_after_login_and_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                first = store.upsert_account('z_first', ID, '', 'test')
                second = store.upsert_account('a_second', OTHER, '', 'test')
                store.mark_account_logged_in(second, '2099-01-01 00:00:00 +0000')
                store.upsert_account('z_first', ID, '', 'updated')
                rows, _ = store.list_accounts_page(0, 10)
                self.assertEqual([row['id'] for row in rows], [first, second])
                self.assertEqual([account.account_id for batch in main.AccountStore.account_batches(
                    store.db_path, [second, first]) for account in batch], [first, second])
            finally:
                store.close()

    def test_result_is_delivered_before_resolving_next_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                first = add_placeholder(store, 'first')
                second = add_placeholder(store, 'second')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                delivered_before_second = []
                progress_at_requests = []
                def resolve(name, _password):
                    if name == 'second':
                        results = [payload for kind, payload in app.events.queue if kind == 'result_batch']
                        delivered_before_second.append([item[0] for batch in results for item in batch])
                        return OTHER
                    return ID
                def request(_key, ids):
                    progress = [payload[1] for kind, payload in app.events.queue if kind == 'resolve_progress']
                    progress_at_requests.append(progress[-1] if progress else 0)
                    return {steam_id: player(steam_id) for steam_id in ids}
                with patch.object(steam_login, 'resolve_steam_id', side_effect=resolve), \
                     patch.object(main, 'request_player_bans', side_effect=request), \
                     patch.object(main.time, 'sleep'):
                    app._query_worker('test-key', [second, first], 2, path)
                self.assertEqual(delivered_before_second, [[first]],
                                 'Finish and deliver the first account before resolving the next')
                self.assertEqual(progress_at_requests, [0, 1], 'ID resolution alone must not advance query completion')
                self.assertEqual(list(app.events.queue)[-1], ('query_done', 2))
            finally:
                store.close()

    def test_incomplete_ban_result_is_not_a_success_or_safe_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                first = store.upsert_account('unknown', ID, '', 'test')
                store.upsert_account('safe', OTHER, '', 'test')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                def response(_key, ids):
                    return {steam_id: {**player(steam_id), 'EconomyBan': 'unknown' if steam_id == ID else 'none'}
                            for steam_id in ids}
                with patch.object(main, 'request_player_bans', side_effect=response), patch.object(main.time, 'sleep'):
                    app._query_worker('test-key', None, 2, path)
                for kind, payload in app.events.queue:
                    if kind == 'result_batch':
                        store.save_results_batch(payload)
                self.assertEqual(store.connection.execute('SELECT status FROM accounts WHERE id=?',
                                                          (first,)).fetchone()[0], '查询失败')
                self.assertEqual(store.count_accounts('safe'), 1)
                self.assertEqual(store.count_accounts('risk'), 1)
            finally:
                store.close()

    def test_primary_timeout_retries_before_using_partner_host(self):
        with patch.object(main, 'urlopen', side_effect=[URLError('timed out'),
                          Response({'players': [player()]})]) as request, \
             patch.object(main.time, 'sleep'):
            self.assertIn(ID, main.request_player_bans('test-key', [ID]))
        self.assertEqual(request.call_count, 2)
        self.assertTrue(all(call.args[0].full_url.startswith(main.API_URLS[0]) for call in request.call_args_list))

    def test_transient_server_error_retries_and_recovers(self):
        error = HTTPError(main.API_URLS[0], 503, 'Unavailable', {}, io.BytesIO())
        with patch.object(main, 'urlopen', side_effect=[error, Response({'players': [player()]})]), \
             patch.object(main.time, 'sleep'):
            self.assertIn(ID, main.request_player_bans('test-key', [ID]))

    def test_rate_limit_respects_retry_after(self):
        error = HTTPError(main.API_URLS[0], 429, 'Too many requests', {'Retry-After': '3'}, io.BytesIO())
        with patch.object(main, 'urlopen', side_effect=[error, Response({'players': [player()]})]), \
             patch.object(main.time, 'sleep') as sleep:
            self.assertIn(ID, main.request_player_bans('test-key', [ID]))
        sleep.assert_called_once_with(3.0)

    def test_retry_wait_can_be_cancelled_before_another_request(self):
        cancellation = threading.Event()
        def cancel_during_wait(_delay):
            cancellation.set()
            return True
        with patch.object(main, 'urlopen', side_effect=URLError('timed out')) as request, \
             patch.object(cancellation, 'wait', side_effect=cancel_during_wait):
            with self.assertRaisesRegex(main.SteamApiFatalError, '取消'):
                main.request_player_bans('test-key', [ID], cancel_event=cancellation)
        self.assertEqual(request.call_count, 1)

    def test_repeated_timeouts_have_bounded_retries_and_do_not_claim_key_revoked(self):
        def fail(request, **_kwargs):
            if request.full_url.startswith(main.API_URLS[1]):
                raise HTTPError(main.API_URLS[1], 403, 'Forbidden', {}, io.BytesIO())
            raise TimeoutError('timed out')
        with patch.object(main, 'urlopen', side_effect=fail) as request, \
             patch.object(main.time, 'sleep'):
            with self.assertRaises(main.SteamApiFatalError) as error:
                main.request_player_bans('test-key', [ID])
        self.assertIn('连接失败', str(error.exception))
        self.assertNotIn('重新生成', str(error.exception))
        self.assertLessEqual(request.call_count, 6)

    def test_invalid_or_incomplete_records_are_never_counted_as_safe_successes(self):
        for invalid in (None, 'invalid', {'SteamId': ID},
                        {**player(), 'NumberOfGameBans': 'bad'},
                        {**player(), 'NumberOfGameBans': -1},
                        {**player(), 'CommunityBanned': 'false'},
                        {**player(), 'EconomyBan': None}):
            with self.subTest(invalid=invalid), \
                 patch.object(main, 'urlopen', return_value=Response({'players': [invalid, player(OTHER)]})):
                result = main.request_player_bans('test-key', [ID, OTHER])
                self.assertNotIn(ID, result)
                self.assertIn(OTHER, result)

    def test_invalid_top_level_response_is_reported_cleanly(self):
        with patch.object(main, 'urlopen', return_value=Response([])):
            with self.assertRaises(main.SteamApiFatalError):
                main.request_player_bans('test-key', [ID])

    def test_unrequested_ids_are_not_accepted(self):
        with patch.object(main, 'urlopen', return_value=Response({'players': [player(), player(OTHER)]})):
            self.assertEqual(set(main.request_player_bans('test-key', [ID])), {ID})

    def test_both_hosts_reject_key_without_retrying_credentials_errors(self):
        def reject_key(request, **_kwargs):
            raise HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO())
        with patch.object(main, 'urlopen', side_effect=reject_key) as request, \
             patch.object(main.time, 'sleep') as sleep:
            with self.assertRaisesRegex(main.SteamApiFatalError, '拒绝'):
                main.request_player_bans('test-key', [ID])
        self.assertEqual(request.call_count, 2)
        sleep.assert_not_called()

    def test_long_rate_limit_stops_instead_of_retrying_too_early(self):
        error = HTTPError(main.API_URLS[0], 429, 'Too many requests', {'Retry-After': '120'}, io.BytesIO())
        with patch.object(main, 'urlopen', side_effect=error) as request, \
             patch.object(main.time, 'sleep') as sleep:
            with self.assertRaisesRegex(main.SteamApiFatalError, '限流'):
                main.request_player_bans('test-key', [ID])
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_known_id_resets_consecutive_resolution_failure_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store = main.AccountStore(Path(directory) / 'accounts.sqlite3')
            try:
                bad = add_placeholder(store, 'bad')
                good = store.upsert_account('good', ID, '', 'test')
                later = add_placeholder(store, 'later')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                with patch.object(steam_login, 'resolve_steam_id', side_effect=steam_login.SteamAuthError('需要验证码')):
                    resolved, failures, stop, handled = app._resolve_batch_ids(
                        store.account_objects([bad, good, later]), 3, store, 0, 3)
                self.assertIsNone(stop)
                self.assertEqual(failures, 1)
                self.assertEqual(handled, 3)
                self.assertEqual([account.account_id for account in resolved], [good])
            finally:
                store.close()

    def test_selected_placeholder_merge_queries_surviving_account(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.sqlite3'
            store = main.AccountStore(path)
            try:
                canonical = store.upsert_account('existing', ID, '', 'test')
                placeholder = add_placeholder(store, 'placeholder')
                app = main.SteamBanApp.__new__(main.SteamBanApp)
                app.events = queue.Queue()
                with patch.object(steam_login, 'resolve_steam_id', return_value=ID), \
                     patch.object(main, 'request_player_bans', return_value={ID: player()}) as request, \
                     patch.object(main.time, 'sleep'):
                    app._query_worker('test-key', [placeholder], 1, path)
                request.assert_called_once()
                self.assertIn(('query_merged', (placeholder, canonical)), list(app.events.queue))
                batches = [payload for kind, payload in app.events.queue if kind == 'result_batch']
                self.assertEqual([record[0] for batch in batches for record in batch], [canonical])
            finally:
                store.close()

    def test_merged_accounts_are_not_queried_or_counted_twice_across_batches(self):
        for batch_size in (1, 100):
            with self.subTest(batch_size=batch_size), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'accounts.sqlite3'
                store = main.AccountStore(path)
                try:
                    canonical = store.upsert_account('existing', ID, '', 'test')
                    add_placeholder(store, 'one')
                    add_placeholder(store, 'two')
                    app = main.SteamBanApp.__new__(main.SteamBanApp)
                    app.events = queue.Queue()
                    with patch.object(steam_login, 'resolve_steam_id', return_value=ID), \
                         patch.object(main, 'request_player_bans', return_value={ID: player()}) as request, \
                         patch.object(main, 'CONSERVATIVE_BATCH_SIZE', batch_size), \
                         patch.object(main.time, 'sleep'):
                        app._query_worker('test-key', None, 3, path)
                    request.assert_called_once()
                    batches = [payload for kind, payload in app.events.queue if kind == 'result_batch']
                    self.assertEqual([record[0] for batch in batches for record in batch], [canonical])
                    self.assertEqual(store.count_accounts(), 1)
                    self.assertEqual(list(app.events.queue)[-1], ('query_done', 3))
                finally:
                    store.close()


if __name__ == '__main__':
    unittest.main()
