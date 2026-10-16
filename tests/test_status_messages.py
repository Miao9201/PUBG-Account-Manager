"""Keep footer messages concise without confusing login failures with success."""
import queue
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import steam_ban_manager as main


class StatusMessagesTest(unittest.TestCase):
    def test_query_errors_have_short_reasons_and_do_not_expose_details(self):
        for detail, expected in (
            ('Steam 的两个兼容 API 主机都拒绝了当前 Web API Key（HTTP 403）', 'API Key 被拒绝'),
            ('Steam API 连接失败：timed out，备用主机 HTTP 403，不代表 Key 失效', '网络连接失败'),
            ('Steam API 限流（HTTP 429），请稍后重试', '请求过于频繁'),
            ('无法连接 Steam API: HTTP 503', 'Steam 服务不可用'),
            ('Steam API 返回的不是有效 JSON', '接口响应异常'),
            ('Steam API 响应中未找到 players 列表', '接口响应异常'),
            ('连续 5 个账号解析 SteamID64 失败（敏感详情）', 'ID 解析失败'),
            ('无法打开账号数据库：E:/private/account.sqlite3', '账号库访问失败'),
            ('unexpected failure: secret-token/private-path', '未知错误'),
        ):
            with self.subTest(detail=detail):
                self.assertEqual(main.brief_error_reason(detail), expected)

    def test_login_outcomes_have_only_current_result_and_account(self):
        for result, expected in (
            ('已自动登录成功（命令行账号密码，全程没有模拟键盘鼠标）', '登录成功：demo'),
            ('已自动登录成功（Steam 用本机记住的登录信息直接进入）', '登录成功：demo'),
            ('60 秒内没有等到 Steam 登录窗口，也没检测到 Steam 已登录：详细原因', '登录超时：demo'),
            ('命令行账号密码已提交，但 Steam 当时还没连上服务器（代理/VPN 常见）', 'Steam 正在连接服务器'),
            ('命令行账号密码已提交，Steam 仍停在登录窗口：可能需要验证码或密码不正确', '登录未完成：demo'),
            ('未识别的登录结果', '登录未完成：demo'),
        ):
            with self.subTest(result=result):
                self.assertEqual(main.login_status_message('demo', result), expected)

    def test_worker_keeps_steam_configuration_but_omits_explanatory_footer_text(self):
        app = main.SteamBanApp.__new__(main.SteamBanApp)
        app.events = queue.Queue()
        with patch.object(main.steam_login, 'shutdown_steam', return_value=True), \
             patch.object(main.steam_login, 'write_auto_login') as auto_login, \
             patch.object(main.steam_login, 'apply_login_tweaks', return_value=['登录首页改为库']) as tweaks, \
             patch.object(main.steam_login, 'launch_login') as launch, \
             patch.object(main.steam_login, 'automate_steam_login', return_value='已自动登录成功（命令行账号密码）'):
            app._steam_login_worker('steam.exe', 'demo', '76561198000000001', 'synthetic',
                                    1, None, threading.Event())
        auto_login.assert_called_once()
        tweaks.assert_called_once()
        launch.assert_called_once()
        kind, payload = app.events.get_nowait()
        self.assertEqual(kind, 'steam_login_done')
        self.assertEqual(payload[2], '登录成功：demo')


if __name__ == '__main__':
    unittest.main()
