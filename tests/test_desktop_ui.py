"""Exercise page navigation and existing account operations in a disposable profile."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_ban_manager as app_module


def close_app(app):
    for callback in app.root.tk.splitlist(app.root.tk.call('after', 'info')):
        app.root.after_cancel(callback)
    app._on_close()


class DesktopWorkflowTest(unittest.TestCase):
    def test_query_button_uses_checks_then_highlight_then_all_and_filters_unqueried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, 'application_data_directory', return_value=Path(directory)), \
                 patch.object(app_module, 'collect_legacy_account_databases', return_value=[]), \
                 patch.object(app_module.SteamBanApp, 'check_for_updates'):
                root = app_module.ttk.Window(themename='flatly')
                root.withdraw()
                app = app_module.SteamBanApp(root)
                try:
                    ids = [app.store.upsert_account(f'demo_{index}', f'7656119800000000{index}', '', 'synthetic')
                           for index in range(1, 4)]
                    app.refresh_table()
                    app.view.select_page('query')
                    app.api_key_var.set('test-key')
                    app.remember_key_var.set(False)
                    app.tree.selection_set(str(ids[0]))
                    for account_id in ids[1:]:
                        app._toggle_checked(account_id)
                    for expected_ids, expected_total in ((ids[1:], 2), ([ids[0]], 1), (None, 3)):
                        with patch.object(app_module.threading, 'Thread') as thread:
                            app.query_all_button.invoke()
                        self.assertEqual(thread.call_args.kwargs['args'][1], expected_ids)
                        self.assertEqual(app.query_total, expected_total)
                        self.assertEqual(app.query_success_var.get(), '查询成功: 0')
                        self.assertEqual(str(app.unqueried_filter_button['state']), 'disabled')
                        app.events.put(('query_done', expected_total))
                        app._drain_events()
                        app._set_all_checked(False)
                        if expected_total == 1:
                            app.tree.selection_remove(app.tree.selection())
                    with patch.object(app_module.threading, 'Thread') as thread, \
                         patch.object(app_module.messagebox, 'showinfo') as info:
                        app.query_selected_button.invoke()
                        thread.assert_not_called()
                        info.assert_called_once()
                        self.assertFalse(app.query_running)
                    app.store.save_result(ids[1], {'NumberOfGameBans': 0, 'CommunityBanned': False, 'EconomyBan': 'none'})
                    app.store.save_result(ids[2], None, 'test failure')
                    # Cancelling the remaining unprocessed row must not hide it from this filter.
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(True)
                    app.events.put(('result_batch', [(ids[1], {'NumberOfGameBans': 0, 'CommunityBanned': False, 'EconomyBan': 'none'}, ''),
                                                     (ids[2], None, 'test failure')]))
                    app.events.put(('query_cancelled', (2, 3)))
                    app._drain_events()
                    app.refresh_table()
                    app.show_only_safe_var.set(True)
                    app._toggle_filter('safe')
                    app.unqueried_filter_button.invoke()
                    self.assertEqual(app._filter_mode(), 'unqueried')
                    self.assertFalse(app.show_only_safe_var.get())
                    self.assertFalse(app.show_only_risk_var.get())
                    self.assertEqual(app.tree.get_children(), (str(ids[0]),))
                    self.assertEqual(app.view.account_total_var.get(), '账号数量: 3')
                    app.show_only_risk_var.set(True)
                    app._toggle_filter('risk')
                    self.assertFalse(app.show_only_unqueried_var.get())
                    self.assertEqual(app.tree.get_children(), (str(ids[2]),))
                    root.geometry('1020x680')
                    root.deiconify()
                    app.view.toggle_sidebar()
                    root.update()
                    for widget in (app.safe_filter_button, app.unqueried_filter_button, app.risk_filter_button):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), widget.master.winfo_width())
                finally:
                    if app.query_running:
                        app.events.put(('query_cancelled', (0, app.query_total)))
                        app._drain_events()
                    close_app(app)

    def test_short_statuses_preserve_cancellation_and_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, 'application_data_directory', return_value=Path(directory)), \
                 patch.object(app_module, 'collect_legacy_account_databases', return_value=[]), \
                 patch.object(app_module.SteamBanApp, 'check_for_updates'), \
                 patch.object(app_module.messagebox, 'showerror') as error_dialog:
                root = app_module.ttk.Window(themename='flatly')
                root.withdraw()
                app = app_module.SteamBanApp(root)
                try:
                    first = app.store.upsert_account('demo', '76561198000000001', '', 'synthetic')
                    app.refresh_table()
                    app.tree.selection_set(str(first))
                    app.api_key_var.set('test-key')
                    app.remember_key_var.set(False)
                    app.status_var.set('尚未设置 API Key')
                    self.assertEqual(app.view.account_status_var.get(), '')
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(False)
                    app.cancel_query()
                    app.events.put(('query_progress', (0, 1)))
                    app.events.put(('resolve_progress', ('demo', 0, 1)))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '正在取消查询…')
                    app.events.put(('query_cancelled', (0, 1)))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '查询已取消：0/1')
                    app.events.put(('query_blocked', (0, 1, '两个主机都拒绝了 Web API Key (HTTP 403)')))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '查询已停止：API Key 被拒绝')
                    self.assertIn('HTTP 403', error_dialog.call_args.args[1])
                    app.import_running = True
                    app.import_cancel_event = threading.Event()
                    app.cancel_import()
                    app.events.put(('import_progress', {'percent': 80}))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '正在取消导入…')
                    app.events.put(('import_done', {'canceled': True, 'imported': 3, 'invalid': 1}))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '导入已取消：已导入／更新 3 条')
                    app.login_running = True
                    app.login_cancel_event = threading.Event()
                    app.events.put(('steam_login_waiting', 12))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '等待 Steam 登录：12 秒')
                    app.cancel_steam_login()
                    app.events.put(('steam_login_waiting', 15))
                    app.events.put(('steam_login_stalled', 'Steam 还在连接 Steam 服务器'))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '正在取消登录…')
                    app.events.put(('steam_login_cancelled', None))
                    app._drain_events()
                    self.assertEqual(app.status_var.get(), '登录已取消')
                    self.assertEqual(app.query_success_var.get(), '查询成功: 0')
                    self.assertEqual(app.view.account_total_var.get(), '账号数量: 1')
                    self.assertEqual(app.view.banned_count_var.get(), '封禁账号: 0')
                finally:
                    if app.query_running:
                        app.events.put(('query_cancelled', (0, app.query_total)))
                        app._drain_events()
                    close_app(app)

    def test_checks_stay_separate_from_single_highlight_and_results_refresh_live(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with patch.object(app_module, 'application_data_directory', return_value=data), \
                 patch.object(app_module, 'collect_legacy_account_databases', return_value=[]), \
                 patch.object(app_module.SteamBanApp, 'check_for_updates'):
                root = app_module.ttk.Window(themename='flatly')
                root.withdraw()
                app = app_module.SteamBanApp(root)
                try:
                    first = app.store.upsert_account('first', '76561198000000001', '', 'test')
                    second = app.store.upsert_account('second', '76561198000000002', '', 'test')
                    app.view.select_page('query')
                    app.refresh_table()
                    app.tree.selection_set(str(first))
                    app._set_all_checked(True)
                    app.api_key_var.set('test-key')
                    app.remember_key_var.set(False)
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(False)
                    self.assertEqual(app.checked_ids, {first, second})
                    self.assertEqual(app.tree.selection(), (str(first),))
                    self.assertEqual(str(app.tree['selectmode']), 'browse')
                    app.events.put(('query_state', ([first], '正在查询')))
                    app.events.put(('result_batch', [(first, {'NumberOfGameBans': 1,
                                    'CommunityBanned': False, 'EconomyBan': 'none'}, '')]))
                    app.events.put(('query_state', ([second], '正在查询')))
                    app._drain_events()
                    self.assertTrue(app.query_running)
                    self.assertEqual(app.tree.selection(), (str(first),))
                    self.assertEqual(app.tree.set(str(first), 'query_status'), '查询成功')
                    self.assertEqual(app.tree.set(str(first), 'pubg'), '封禁')
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '正在查询')
                    self.assertEqual(app.query_success_var.get(), '查询成功: 1')
                    app.events.put(('result_batch', [(second, {'NumberOfGameBans': 0,
                                    'CommunityBanned': False, 'EconomyBan': 'none'}, '')]))
                    app.events.put(('query_done', 2))
                    app._drain_events()
                    self.assertEqual(app.tree.set(str(second), 'pubg'), '未封禁')
                    self.assertEqual(app.store.count_accounts('risk'), 1)
                    self.assertEqual(app.store.count_accounts('safe'), 1)
                    self.assertEqual(app.tree.selection(), (str(first),))
                finally:
                    if app.query_running:
                        app.events.put(('query_cancelled', (0, app.query_total)))
                        app._drain_events()
                    close_app(app)

    def test_merge_after_success_keeps_result_when_query_is_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with patch.object(app_module, 'application_data_directory', return_value=data), \
                 patch.object(app_module, 'collect_legacy_account_databases', return_value=[]), \
                 patch.object(app_module.SteamBanApp, 'check_for_updates'):
                root = app_module.ttk.Window(themename='flatly')
                root.withdraw()
                app = app_module.SteamBanApp(root)
                try:
                    canonical = app.store.upsert_account('existing', '76561198000000001', '', 'test')
                    with app.store.connection:
                        app.store.connection.execute(app.store.UPSERT_SQL,
                                                     ('placeholder', 'placeholder', '', 'test', app_module.utc_now()))
                    placeholder = app.store.connection.execute("SELECT id FROM accounts WHERE steam_id='placeholder'").fetchone()[0]
                    app.api_key_var.set('test-key')
                    app.remember_key_var.set(False)
                    app.refresh_table()
                    app.checked_ids = {placeholder}
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(True)
                    app.store.update_steam_id(placeholder, '76561198000000001')
                    app.events.put(('result_batch', [(canonical, {'NumberOfGameBans': 1}, '')]))
                    app.events.put(('query_merged', (placeholder, canonical)))
                    app._drain_events()
                    self.assertEqual(app.checked_ids, {canonical})
                    self.assertNotIn(canonical, app.query_pending_ids)
                    app.cancel_query()
                    app.events.put(('query_cancelled', (1, 2)))
                    app._drain_events()
                    self.assertEqual(app.query_success_var.get(), '查询成功: 1')
                    row = app.store.connection.execute('SELECT status, game_bans FROM accounts WHERE id=?',
                                                       (canonical,)).fetchone()
                    self.assertEqual(tuple(row), ('查询成功', 1))
                finally:
                    close_app(app)

    def test_navigation_preserves_accounts_and_existing_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            store = app_module.AccountStore(data / app_module.ACCOUNT_DATABASE_FILENAME)
            first = store.upsert_account('demo_one', '76561198000000001', '演示', 'demo-password')
            second = store.upsert_account('demo_two', '76561198000000002', '演示', 'other-password')
            store.close()
            with patch.object(app_module, 'application_data_directory', return_value=data), \
                 patch.object(app_module, 'collect_legacy_account_databases', return_value=[]), \
                 patch.object(app_module.SteamBanApp, 'check_for_updates'):
                root = app_module.ttk.Window(themename='flatly')
                callback_errors = []
                root.report_callback_exception = lambda kind, error, trace: callback_errors.append(str(error))
                root.withdraw()
                app = app_module.SteamBanApp(root)
                try:
                    self.assertTrue(hasattr(app, 'view'), 'The window needs working sidebar pages')
                    view = app.view
                    root.deiconify()
                    root.update()
                    app.tree.selection_set(str(first))
                    root.update()
                    self.assertTrue(view.account_footer.winfo_ismapped())
                    self.assertEqual(view.account_total_var.get(), '账号数量: 2')
                    app._toggle_checked(second)
                    app._menu_account_id = first
                    with patch.object(app_module, 'AccountDialog') as editor, \
                         patch.object(root, 'wait_window'):
                        editor.return_value.result = None
                        app.row_menu.invoke(1)
                        self.assertEqual(editor.call_args.args[2].account_id, first,
                                         'Editing a context row must ignore another checked account')
                        self.assertEqual(app.checked_ids, {second})
                    view.nav_buttons['query'].invoke()
                    root.update()
                    self.assertTrue(app.tree.winfo_ismapped())
                    self.assertTrue(app.query_all_button.winfo_ismapped())
                    self.assertFalse(view.account_footer.winfo_ismapped())
                    self.assertTrue(view.query_footer.winfo_ismapped())
                    self.assertEqual(view.query_selected_var.get(), '当前选中: 1 个')
                    self.assertIn('pubg', app.tree['displaycolumns'])
                    self.assertNotIn('row_actions', app.tree['displaycolumns'])
                    self.assertIn('query_status', app.tree['displaycolumns'])
                    self.assertIn('steam_id', app.tree['displaycolumns'])
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '未查询')
                    self.assertEqual(app.tree.set(str(second), 'steam_id'), '')
                    # Migrated successful rows may not carry the original API JSON.
                    with app.store.connection:
                        app.store.connection.execute("UPDATE accounts SET status='查询成功' WHERE id=?", (first,))
                    app.refresh_table()
                    self.assertEqual(app.tree.set(str(first), 'steam_id'), '76561198000000001')
                    app.tree.selection_set(str(first))
                    root.after(180, root.quit)
                    root.mainloop()
                    self.assertEqual(view.row_buttons, {})
                    self.assertIn(str(second), view.row_checkboxes)
                    self.assertEqual(app.tree.selection(), (str(first),))
                    self.assertEqual(app.checked_ids, {second})

                    view.nav_buttons['settings'].invoke()
                    root.update()
                    self.assertTrue(app.key_entry.winfo_ismapped())
                    self.assertFalse(app.tree.winfo_ismapped())
                    self.assertFalse(view.account_footer.winfo_ismapped())
                    self.assertFalse(view.query_footer.winfo_ismapped())
                    app.api_key_var.set('isolated-ui-test-key')
                    app.save_api_key()
                    self.assertEqual(app.key_store.load(), 'isolated-ui-test-key')
                    view.nav_buttons['about'].invoke()
                    root.update()
                    self.assertFalse(view.account_footer.winfo_ismapped())
                    self.assertFalse(view.query_footer.winfo_ismapped())

                    view.menu_button.invoke()
                    root.update()
                    self.assertGreater(view.sidebar.winfo_width(), 150)
                    view.menu_button.invoke()
                    root.update()
                    self.assertLess(view.sidebar.winfo_width(), 80)
                    view.nav_buttons['accounts'].invoke()
                    root.update()
                    self.assertEqual(set(app.tree.get_children()), {str(first), str(second)})
                    self.assertEqual(app.checked_ids, {second})
                    self.assertTrue(app.steam_login_button.winfo_ismapped())
                    self.assertFalse(app.key_entry.winfo_ismapped())

                    # Query statistics track this run, including partial failures and resets.
                    view.nav_buttons['query'].invoke()
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(False)
                    self.assertEqual(app.status_var.get(), '开始查询：1 个账号')
                    self.assertEqual(app.query_total, 1)
                    self.assertEqual(app.query_success_var.get(), '查询成功: 0')
                    app.events.put(('query_state', ([second], '正在查询')))
                    app._drain_events()
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '正在查询')
                    app.events.put(('result_batch', [(second, {'NumberOfGameBans': 1}, '')]))
                    app.events.put(('query_done', 1))
                    app._drain_events()
                    self.assertEqual(app.query_success_var.get(), '查询成功: 1')
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '查询成功')
                    self.assertEqual(app.tree.set(str(second), 'steam_id'), '76561198000000002')
                    self.assertEqual(view.banned_count_var.get(), '封禁账号: 1')
                    self.assertEqual(view.account_total_var.get(), '账号数量: 2')
                    app.show_only_safe_var.set(True)
                    app._toggle_filter('safe')
                    self.assertEqual(view.account_total_var.get(), '账号数量: 2')
                    self.assertEqual(view.banned_count_var.get(), '封禁账号: 1')
                    self.assertEqual(view.query_selected_var.get(), '当前选中: 0 个')
                    app.show_only_safe_var.set(False)
                    app.refresh_table()
                    app._toggle_checked(second)
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(True)
                    self.assertEqual(app.status_var.get(), '开始查询：2 个账号')
                    self.assertEqual(app.query_success_var.get(), '查询成功: 0')
                    app.events.put(('result_batch', [(first, {}, ''), (second, None, '接口未返回账号')]))
                    app.events.put(('query_done', 2))
                    app._drain_events()
                    self.assertEqual(app.query_success_var.get(), '查询成功: 1')
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '查询失败')

                    # Cancellation preserves completed results and affects only unfinished targets.
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(True)
                    app.events.put(('result_batch', [(first, {}, '')]))
                    app._drain_events()
                    app.cancel_query()
                    self.assertTrue(app.query_running, 'Keep controls locked until the worker acknowledges')
                    self.assertTrue(app.query_cancel_event.is_set())
                    app.events.put(('query_cancelled', (1, 2)))
                    app._drain_events()
                    self.assertFalse(app.query_running)
                    self.assertEqual(app.tree.set(str(first), 'query_status'), '查询成功')
                    self.assertEqual(app.tree.set(str(second), 'query_status'), '已取消')
                    self.assertEqual(app.query_success_var.get(), '查询成功: 1')
                    self.assertEqual(app.store.connection.execute('SELECT status FROM accounts WHERE id=?',
                                                                  (second,)).fetchone()[0], '已取消')
                    view.nav_buttons['accounts'].invoke()
                    root.update()
                    self.assertIn('row_actions', app.tree['displaycolumns'])
                    self.assertNotIn('query_status', app.tree['displaycolumns'])

                    app.show_password_var.set(True)
                    app._toggle_password_visibility()
                    self.assertEqual(app.tree.set(str(first), 'password'), 'demo-password')
                    app._set_controls(False)
                    self.assertEqual(str(app.steam_login_button['state']), 'disabled')
                    app._set_controls(True)
                    self.assertEqual(str(app.steam_login_button['state']), 'normal')

                    # A row's delete action must not delete another checked account.
                    with patch.object(app_module.messagebox, 'askyesno', return_value=False):
                        view.delete_row(first)
                    self.assertEqual(app.store.count_accounts('all'), 2)
                    self.assertEqual(app.checked_ids, {second})
                    with patch.object(app_module.messagebox, 'askyesno', return_value=True):
                        view.delete_row(first)
                    self.assertEqual(app.store.count_accounts('all'), 1)
                    self.assertEqual(view.account_total_var.get(), '账号数量: 1')
                    self.assertEqual(app.checked_ids, {second})
                    self.assertTrue(app.tree.exists(str(second)))

                    # Deleting a visible row must retain checks beyond the first loaded chunk.
                    app.store.upsert_account('demo_three', '76561198000000003', '演示', 'third')
                    fourth = app.store.upsert_account('demo_four', '76561198000000004', '演示', 'fourth')
                    with patch.object(app_module, 'TREE_LOAD_CHUNK', 1):
                        app.refresh_table()
                        app._load_more_if_needed()
                        app._load_more_if_needed()
                        self.assertTrue(app.tree.exists(str(second)))
                        with patch.object(app_module.messagebox, 'askyesno', return_value=True):
                            view.delete_row(fourth)
                        self.assertEqual(app.checked_ids, {second})
                        self.assertEqual(app.store.account_password(second), 'other-password')

                    view.nav_buttons['query'].invoke()
                    app._set_query_progress(1, 2)
                    root.update()
                    self.assertTrue(app.query_progress_card.winfo_ismapped())
                    self.assertEqual(float(app.query_progress_bar['value']), 50)
                    view.nav_buttons['settings'].invoke()
                    view.nav_buttons['query'].invoke()
                    root.update()
                    self.assertTrue(app.query_progress_card.winfo_ismapped())

                    root.geometry('1100x720')
                    root.update()
                    self.assertGreater(app.tree.winfo_height(), 200)
                    self.assertLessEqual(app.query_all_button.winfo_rootx() + app.query_all_button.winfo_width(),
                                         root.winfo_rootx() + root.winfo_width())
                    root.geometry('1020x680')
                    view.menu_button.invoke()
                    root.update()
                    self.assertEqual(app.tree.xview(), (0.0, 1.0))
                    for column in app.tree['displaycolumns']:
                        x, _y, width, _height = app.tree.bbox(str(second), column)
                        self.assertGreaterEqual(x, 0)
                        self.assertLessEqual(x + width, app.tree.winfo_width())
                    view.menu_button.invoke()
                    self.assertEqual(callback_errors, [], 'UI callbacks must not fail silently')

                    view.nav_buttons['accounts'].invoke()
                    root.update()
                    root.after(180, root.quit)
                    root.mainloop()
                    target = app.tree.get_children()[0]
                    if int(target) in app.checked_ids:
                        app._toggle_checked(int(target))
                    view.row_checkboxes[target].invoke()
                    self.assertIn(int(target), app.checked_ids)
                    view.row_checkboxes[target].invoke()
                    self.assertNotIn(int(target), app.checked_ids)

                    view.nav_buttons['settings'].invoke()
                    app.auto_delete_wrong_password_button.invoke()
                    self.assertTrue(app.store.auto_delete_wrong_password_enabled())
                    app.login_running = True
                    app.events.put(('steam_login_invalid_password', (second, 'demo_two', 'outdated-password')))
                    app._drain_events()
                    self.assertEqual(app.store.account_password(second), 'other-password')
                    app.login_running = True
                    app.login_cancel_event = threading.Event()
                    app.login_cancel_event.set()
                    app.events.put(('steam_login_invalid_password', (second, 'demo_two', 'other-password')))
                    app._drain_events()
                    self.assertEqual(app.store.account_password(second), 'other-password')
                    app.events.put(('steam_login_invalid_password', (second, 'demo_two', 'other-password')))
                    app._drain_events()
                    self.assertIsNone(app.store.connection.execute('SELECT id FROM accounts WHERE id=?', (second,)).fetchone())
                    self.assertFalse(app.login_running)
                    self.assertEqual(callback_errors, [])

                    # Closing waits for query acknowledgement and saves already queued results.
                    closing_id = app.store.upsert_account('closing', '76561198000000009', '', 'test')
                    app.show_only_safe_var.set(False)
                    app.show_only_risk_var.set(False)
                    with patch.object(app_module.threading, 'Thread'):
                        app.start_query(True)
                    app.events.put(('result_batch', [(closing_id, {}, '')]))
                    with patch.object(root, 'after'), patch.object(root, 'destroy') as destroy:
                        app._on_close()
                        destroy.assert_not_called()
                        self.assertTrue(app.query_running)
                        self.assertTrue(app.query_cancel_event.is_set())
                        app.events.put(('query_cancelled', (1, app.query_total)))
                        app._drain_events()
                        row = app.store.connection.execute('SELECT status, api_bans_json FROM accounts WHERE id=?',
                                                           (closing_id,)).fetchone()
                        self.assertEqual(row['status'], '查询成功')
                        self.assertEqual(row['api_bans_json'], '{}')
                        self.assertEqual(str(app.query_all_button['state']), 'disabled')
                finally:
                    close_app(app)


if __name__ == '__main__':
    unittest.main()
