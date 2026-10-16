"""Fluent-style presentation for the existing account manager and its commands."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
import ttkbootstrap as ttk

BG = '#E4E0E3'
RAIL = '#BCB8C1'
CARD = '#FAF9FA'
LINE = '#D3CFD4'
TEXT = '#202020'
MUTED = '#625E64'
BLUE = '#0078D4'
FONT = 'Microsoft YaHei UI'


def rounded(canvas, x1, y1, x2, y2, radius=7, **options):
    return canvas.create_polygon(
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        smooth=True, splinesteps=24, **options,
    )


class ActionButton(tk.Canvas):
    """A rounded, keyboard-accessible button with the normal widget state API."""
    def __init__(self, parent, text, command, *, primary=False, width=None, state='normal'):
        self.caption, self.command = text, command
        self.primary, self.button_state = primary, state
        self.hover = False
        self.font = tkfont.Font(family=FONT, size=10)
        self.fixed_width = width
        super().__init__(parent, width=width or self.font.measure(text) + 28, height=34,
                         bg=parent.cget('bg') if 'bg' in parent.keys() else CARD,
                         highlightthickness=0, takefocus=True, cursor='hand2')
        self.bind('<Configure>', self._draw)
        self.bind('<Enter>', lambda _e: self._set_hover(True))
        self.bind('<Leave>', lambda _e: self._set_hover(False))
        self.bind('<ButtonRelease-1>', lambda e: self.invoke() if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height() else None)
        self.bind('<Return>', lambda _e: self.invoke())
        self.bind('<space>', lambda _e: self.invoke())
        self.bind('<FocusIn>', self._draw)
        self.bind('<FocusOut>', self._draw)

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _draw(self, _event=None):
        self.delete('all')
        disabled = self.button_state == 'disabled'
        fill = '#F0EEF0' if disabled else ('#006CBD' if self.hover else BLUE) if self.primary else ('#F0EDF0' if self.hover else '#FCFBFC')
        foreground = '#A5A0A6' if disabled else '#FFFFFF' if self.primary else TEXT
        border = BLUE if self.focus_get() == self else fill if self.primary else LINE
        rounded(self, 1, 1, max(2, self.winfo_width()-1), max(2, self.winfo_height()-1), 5,
                fill=fill, outline=border, width=1)
        self.create_text(self.winfo_width()/2, self.winfo_height()/2,
                         text=self.caption, fill=foreground, font=self.font)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        for key, attribute in (('text', 'caption'), ('command', 'command'), ('state', 'button_state')):
            if key in kwargs:
                setattr(self, attribute, kwargs.pop(key))
        if hasattr(self, 'font') and not self.fixed_width:
            kwargs['width'] = self.font.measure(self.caption) + 28
        result = super().configure(**kwargs)
        if hasattr(self, 'button_state'):
            self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == 'state':
            return self.button_state
        if key == 'text':
            return self.caption
        return super().cget(key)

    __getitem__ = cget

    def invoke(self):
        if self.button_state != 'disabled' and self.command:
            return self.command()


class Card(tk.Canvas):
    def __init__(self, parent, *, height=100, padding=16):
        super().__init__(parent, bg=parent.cget('bg'), height=height, highlightthickness=0)
        self.padding = padding
        self.body = tk.Frame(self, bg=CARD)
        self.body_window = self.create_window(padding, padding, window=self.body, anchor='nw')
        self.bind('<Configure>', self._resize)

    def _resize(self, _event):
        self.delete('surface')
        rounded(self, 1, 1, self.winfo_width()-1, self.winfo_height()-1, 9,
                fill=CARD, outline=LINE, tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.body_window, width=max(1, self.winfo_width()-2*self.padding),
                           height=max(1, self.winfo_height()-2*self.padding))


class NavButton(tk.Canvas):
    def __init__(self, parent, icon, caption, command):
        super().__init__(parent, width=46, height=42, bg=RAIL, highlightthickness=0,
                         takefocus=True, cursor='hand2')
        self.icon, self.caption, self.command = icon, caption, command
        self.selected = self.expanded = self.hover = False
        self.bind('<Configure>', self.draw)
        self.bind('<ButtonRelease-1>', lambda _e: self.invoke())
        self.bind('<Return>', lambda _e: self.invoke())
        self.bind('<space>', lambda _e: self.invoke())
        self.bind('<Enter>', lambda _e: self.set_hover(True))
        self.bind('<Leave>', lambda _e: self.set_hover(False))
        self.bind('<FocusIn>', self.draw)
        self.bind('<FocusOut>', self.draw)

    def invoke(self):
        return self.command()

    def set_hover(self, value):
        self.hover = value
        self.draw()

    def draw(self, _event=None):
        self.delete('all')
        if self.selected or self.hover or self.focus_get() == self:
            rounded(self, 2, 3, self.winfo_width()-2, 39, 5,
                    fill='#ADA8B2' if self.selected else '#C8C4CC', outline='')
        if self.selected:
            rounded(self, 2, 12, 5, 30, 2, fill=BLUE, outline='')
        self.create_text(24, 21, text=self.icon, fill=TEXT, font=('Segoe MDL2 Assets', 14))
        if self.expanded:
            self.create_text(53, 21, text=self.caption, fill=TEXT, font=(FONT, 10), anchor='w')


class SelectionCell(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, width=24, height=24, bg=CARD, highlightthickness=0,
                         takefocus=True, cursor='hand2')
        self.command = command
        self.checked = False
        self.bind('<ButtonRelease-1>', lambda _e: self.invoke())
        self.bind('<space>', lambda _e: self.invoke())
        self.bind('<Return>', lambda _e: self.invoke())
        self.bind('<FocusIn>', lambda _e: self.draw())
        self.bind('<FocusOut>', lambda _e: self.draw())

    def invoke(self):
        self.command()
        self.checked = not self.checked
        self.draw()

    def draw(self):
        self.delete('all')
        rounded(self, 2, 2, 22, 22, 3, fill=BLUE if self.checked else '#FFFFFF',
                outline=BLUE if self.checked or self.focus_get() == self else '#8A858D')
        if self.checked:
            self.create_line(6, 12, 10, 16, 18, 7, fill='#FFFFFF', width=2.3, capstyle='round', joinstyle='round')


class DesktopView:
    def __init__(self, app, version):
        self.app = app
        self.version = version
        self.root = app.root
        self.page = 'accounts'
        self.expanded = False
        self.row_buttons = {}
        self.row_checkboxes = {}
        self.mirrors = []
        self._configure_styles()
        self.root.configure(bg=BG)
        icon = Path(__file__).resolve().parent / 'assets' / 'app.ico'
        if icon.is_file():
            self.root.iconbitmap(str(icon))
        self.sidebar = tk.Frame(self.root, bg=RAIL, width=54)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self.menu_button = NavButton(self.sidebar, '\ue700', '收起导航', self.toggle_sidebar)
        self.menu_button.pack(fill='x', padx=3, pady=(5, 8))
        self.nav_buttons = {}
        for key, icon, caption in (
            ('accounts', '\ue77b', '账号管理'), ('query', '\ue721', '封禁查询'),
            ('settings', '\ue713', '设置'), ('about', '\ue946', '关于'),
        ):
            button = NavButton(self.sidebar, icon, caption, lambda p=key: self.select_page(p))
            button.pack(fill='x', padx=3)
            self.nav_buttons[key] = button

        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side='left', fill='both', expand=True, padx=24, pady=(20, 18))
        self.header = tk.Frame(self.main, bg=BG)
        self.header.pack(fill='x', pady=(0, 18))
        self.title_var, self.subtitle_var = tk.StringVar(), tk.StringVar()
        self.label(self.header, variable=self.title_var, size=24, bold=True, background=BG).pack(anchor='w')
        self.subtitle_label = self.label(self.header, variable=self.subtitle_var, muted=True, background=BG)
        self.subtitle_label.pack(anchor='w', pady=(5, 0))

        self.account_footer = Card(self.main, height=54, padding=12)
        self.account_footer.body.columnconfigure(0, weight=1)
        self.account_footer.body.rowconfigure(0, weight=1)
        self.account_status_var = tk.StringVar()
        app.status_var.trace_add('write', self._sync_account_status)
        self._sync_account_status()
        self.label(self.account_footer.body, variable=self.account_status_var, muted=True, size=9).grid(row=0, column=0, sticky='ew')
        self.banned_count_var = tk.StringVar(value='封禁账号: 0')
        self.account_total_var = tk.StringVar(value='账号数量: 0')
        for column, (variable, color) in enumerate((
            (self.banned_count_var, '#E62B18'),
            (self.account_total_var, '#005A9E'),
        ), start=1):
            self.label(self.account_footer.body, variable=variable, color=color, bold=True, size=10).grid(
                row=0, column=column, sticky='e', padx=(24, 0))

        self.query_footer = Card(self.main, height=54, padding=12)
        self.query_footer.body.columnconfigure(0, weight=1)
        self.query_footer.body.rowconfigure(0, weight=1)
        self.label(self.query_footer.body, variable=app.status_var, muted=True, size=9).grid(row=0, column=0, sticky='ew')
        self.query_selected_var = tk.StringVar(value='当前选中: 0 个')
        for column, (variable, color) in enumerate((
            (app.query_success_var, '#138313'),
            (self.account_total_var, '#005A9E'),
            (self.query_selected_var, '#005A9E'),
        ), start=1):
            self.label(self.query_footer.body, variable=variable, color=color, bold=True, size=10).grid(
                row=0, column=column, sticky='e', padx=(24, 0))

        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill='both', expand=True)
        self.list_area = tk.Frame(self.content, bg=BG)
        self._build_toolbars()
        self._build_table()
        self._build_settings()
        self._build_about()
        self.select_page('accounts')
        self.root.after(120, self._sync_row_actions)

    @staticmethod
    def label(parent, text='', *, variable=None, size=10, bold=False, muted=False,
              background=None, color=None, **kwargs):
        return tk.Label(parent, text=text, textvariable=variable,
                        bg=background or parent.cget('bg'), fg=color or (MUTED if muted else TEXT),
                        font=(FONT, size, 'bold' if bold else 'normal'), anchor='w', **kwargs)

    def _sync_account_status(self, *_args):
        message = self.app.status_var.get()
        self.account_status_var.set('' if message == '尚未设置 API Key' else message)

    def _configure_styles(self):
        style = ttk.Style()
        for name in ('TFrame', 'Card.TFrame'):
            style.configure(name, background=CARD, borderwidth=0, relief='flat')
        for name in ('TLabel', 'Body.TLabel', 'Hint.TLabel', 'SectionTitle.TLabel'):
            style.configure(name, background=CARD, foreground=MUTED if name == 'Hint.TLabel' else TEXT,
                            font=(FONT, 10), borderwidth=0)
        style.configure('SectionTitle.TLabel', font=(FONT, 12, 'bold'))
        style.configure('TButton', font=(FONT, 10), padding=(12, 7))
        style.configure('TCheckbutton', background=CARD, foreground=TEXT, font=(FONT, 10))
        style.configure('Fluent.TEntry', padding=(10, 8), fieldbackground='#FFFFFF', foreground=TEXT, font=(FONT, 10))
        style.configure('Fluent.Treeview', background=CARD, fieldbackground=CARD, foreground=TEXT,
                        rowheight=42, font=(FONT, 10), borderwidth=0, relief='flat')
        style.map('Fluent.Treeview', background=[('selected', BLUE)], foreground=[('selected', '#FFFFFF')])
        style.configure('Fluent.Treeview.Heading', background='#FFFFFF', foreground=TEXT,
                        font=(FONT, 9), padding=(10, 10), relief='flat', borderwidth=0)
        style.map('Fluent.Treeview.Heading', background=[('active', '#F0EDF0')])

    def _button(self, parent, name, caption, callback, **options):
        button = ActionButton(parent, caption, callback, **options)
        setattr(self.app, name, button)
        button.pack(side='left', padx=(0, 8))
        return button

    def _mirror(self, parent, caption, source):
        button = ActionButton(parent, caption, source.invoke)
        self.mirrors.append((button, source))
        return button

    def _build_toolbars(self):
        a = self.app
        self.account_toolbar = tk.Frame(self.list_area, bg=BG)
        self._button(self.account_toolbar, 'paste_import_button', '+  粘贴导入', a.import_pasted_accounts)
        self._button(self.account_toolbar, 'import_button', '↤  导入文件', a.import_accounts)
        self._button(self.account_toolbar, 'steam_login_button', '一键登录', a.open_steam_login)
        self._button(self.account_toolbar, 'edit_button', '编辑所选', a.edit_selected)
        self._button(self.account_toolbar, 'delete_button', '删除所选', a.delete_selected)
        self._button(self.account_toolbar, 'export_accounts_button', '导出账号', a.export_accounts)
        self._button(self.account_toolbar, 'cancel_import_button', '取消导入', a.cancel_import, state='disabled')
        self._button(self.account_toolbar, 'cancel_login_button', '取消登录', a.cancel_steam_login, state='disabled')
        self.query_toolbar = tk.Frame(self.list_area, bg=BG)
        self._button(self.query_toolbar, 'query_all_button', '▷  查询封禁', a.start_query, primary=True)
        self._button(self.query_toolbar, 'query_selected_button', '查询所选', lambda: a.start_query(False))
        self._mirror(self.query_toolbar, '导出账号', a.export_accounts_button).pack(side='left', padx=(0, 8))
        self._button(self.query_toolbar, 'cancel_query_button', '取消查询', a.cancel_query, state='disabled')
        self.filters = Card(self.list_area, height=58, padding=12)
        self.filters.pack(fill='x', pady=(0, 14))
        f = self.filters.body
        self._button(f, 'select_all_button', '全选', lambda: a._set_all_checked(True), width=70)
        self._button(f, 'clear_checked_button', '清空勾选', lambda: a._set_all_checked(False), width=92)
        a.show_password_button = ttk.Checkbutton(f, text='显示密码', variable=a.show_password_var, command=a._toggle_password_visibility)
        a.show_password_button.pack(side='left', padx=(14, 16))
        a.safe_filter_button = ttk.Checkbutton(f, text='仅无风险', variable=a.show_only_safe_var, command=lambda: a._toggle_filter('safe'))
        a.safe_filter_button.pack(side='left', padx=(0, 16))
        a.unqueried_filter_button = ttk.Checkbutton(f, text='仅未查询', variable=a.show_only_unqueried_var, command=lambda: a._toggle_filter('unqueried'))
        a.unqueried_filter_button.pack(side='left', padx=(0, 16))
        a.risk_filter_button = ttk.Checkbutton(f, text='仅有风险 / 异常', variable=a.show_only_risk_var, command=lambda: a._toggle_filter('risk'))
        a.risk_filter_button.pack(side='left')
        a.query_progress_card = Card(self.list_area, height=54, padding=10)
        self.label(a.query_progress_card.body, variable=a.query_progress_var, size=9, muted=True).pack(side='left', padx=(0, 16))
        a.query_progress_bar = ttk.Progressbar(a.query_progress_card.body, maximum=100, mode='determinate')
        a.query_progress_bar.pack(side='left', fill='x', expand=True, pady=8)

    def _build_table(self):
        a = self.app
        a.table_card = Card(self.list_area, padding=2)
        a.table_card.pack(fill='both', expand=True)
        frame = a.table_card.body
        names = [name for name, _label, _width in a.columns] + ['row_actions']
        a.tree = ttk.Treeview(frame, columns=names, show='headings', selectmode='browse', style='Fluent.Treeview')
        for name, caption, width in a.columns:
            a.tree.heading(name, text=caption, anchor='center')
            a.tree.column(name, width=width, minwidth=45, anchor='center')
        a.tree.heading('row_actions', text='操作', anchor='center')
        a.tree.column('row_actions', width=200, minwidth=45, stretch=False, anchor='center')
        a.tree.column('pick', width=64, minwidth=64, stretch=False)
        a.tree.bind('<Configure>', self._fit_table_columns)
        a.tree.tag_configure('risk', background='#FFF0EE')
        a.tree.tag_configure('failure', background='#FFF6E7')
        a.tree.tag_configure('success', background='#F3F9F4')
        a.tree.bind('<Button-1>', a._on_tree_click, add='+')
        a.tree.bind('<Double-1>', a._on_tree_double_click)
        a.tree.bind('<Button-3>', a._on_tree_right_click)
        a.tree.bind('<Delete>', lambda _e: a.delete_selected() if self.page == 'accounts' else None)
        a.tree.bind('<<TreeviewSelect>>', self.refresh_query_selection)
        a.tree.bind('<MouseWheel>', a._queue_load_more, add='+')
        a.tree.bind('<Button-4>', a._queue_load_more, add='+')
        a.tree.bind('<Button-5>', a._queue_load_more, add='+')
        a.row_menu = tk.Menu(self.root, tearoff=0, font=(FONT, 10))
        a.row_menu.add_command(label='登录该账号', command=lambda: a.open_steam_login(a._menu_account_id))
        a.row_menu.add_command(label='编辑该账号', command=lambda: a.edit_selected(a._menu_account_id))
        a.row_menu.add_separator()
        a.row_menu.add_command(label='删除所选账号', command=a.delete_selected)
        a.y_scroll = ttk.Scrollbar(frame, orient='vertical', command=a._scroll_tree)
        a.tree.configure(yscrollcommand=a._on_tree_yview)
        a.tree.grid(row=0, column=0, sticky='nsew')
        a.y_scroll.grid(row=0, column=1, sticky='ns')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

    def _fit_table_columns(self, _event=None):
        tree = self.app.tree
        if tree.winfo_width() <= 2:
            return
        if self.page == 'query':
            # Keep the previous status/ban widths; give ID the former login allocation.
            previous_available = max(180, tree.winfo_width() - 64 - 88 - 168 - 2)
            ban_width = max(45, int(previous_available * 120 / 650))
            id_width = max(168, int(previous_available * 205 / 650))
            for column, width in (('query_status', 88), ('pubg', ban_width), ('steam_id', id_width)):
                tree.column(column, width=width, minwidth=45, stretch=False)
            available = tree.winfo_width() - 64 - 88 - ban_width - id_width - 2
            columns = ('account_name', 'password', 'login_elapsed')
        else:
            available = tree.winfo_width() - 64 - 2
            columns = ('account_name', 'password', 'login_elapsed', 'pubg', 'row_actions')
        width, remainder = divmod(max(45 * len(columns), available), len(columns))
        for index, column in enumerate(columns):
            tree.column(column, width=width + (index < remainder), minwidth=45, stretch=False)
        tree.xview_moveto(0)

    def _build_settings(self):
        a = self.app
        self.settings = tk.Frame(self.content, bg=BG)
        inner = self.settings
        inner.columnconfigure(0, weight=1, uniform='settings')
        inner.columnconfigure(1, weight=1, uniform='settings')
        for column, caption in enumerate(('连接与凭据', '数据管理')):
            self.label(inner, caption, size=15, background=BG).grid(row=0, column=column, sticky='w', pady=(0, 12), padx=(0, 22) if column == 0 else 0)
        key_card = Card(inner, height=292)
        key_card.grid(row=1, column=0, sticky='nsew', padx=(0, 22))
        k = key_card.body
        self.label(k, 'Steam Web API Key', bold=True).pack(anchor='w')
        self.label(k, '用于查询 Steam 公开封禁信息，自动登录无需填写。', muted=True, size=9).pack(anchor='w', pady=(5, 12))
        a.key_entry = ttk.Entry(k, textvariable=a.api_key_var, show='●', style='Fluent.TEntry')
        a.key_entry.pack(fill='x')
        buttons = tk.Frame(k, bg=CARD)
        buttons.pack(fill='x', pady=(12, 14))
        self._button(buttons, 'save_key_button', '保存 Key', a.save_api_key, primary=True)
        self._button(buttons, 'clear_saved_key_button', '清除保存', a.clear_saved_api_key)
        a.api_key_application_link = self.label(k, '申请 Steam Web API Key  ↗', color=BLUE, cursor='hand2', takefocus=True)
        a.api_key_application_link.pack(anchor='w')
        a.api_key_application_link.bind('<Button-1>', a._open_api_key_application_page)
        a.api_key_application_link.bind('<Return>', a._open_api_key_application_page)
        data_card = Card(inner, height=292)
        data_card.grid(row=1, column=1, sticky='nsew')
        for index, (caption, description, source) in enumerate((
            ('导出账号数据', '可选择 CSV、JSON 或 TXT 格式。', a.export_accounts_button),
            ('导入账号文件', '支持 CSV / JSON / TXT，沿用当前导入规则。', a.import_button),
            ('粘贴导入账号', '每行一个账号，使用 账号----密码 格式。', a.paste_import_button),
        )):
            if index:
                tk.Frame(data_card.body, bg='#E5E1E5', height=1).pack(fill='x', pady=10)
            self._mirror(data_card.body, caption, source).pack(anchor='w')
            self.label(data_card.body, description, size=9, muted=True).pack(anchor='w', pady=(4, 0))
        for column, caption in enumerate(('账号显示', '账号清理')):
            self.label(inner, caption, size=15, background=BG).grid(row=2, column=column, sticky='w', pady=(24, 12))
        display = Card(inner, height=154)
        display.grid(row=3, column=0, sticky='nsew', padx=(0, 22), pady=(0, 4))
        self.label(display.body, '密码显示', bold=True).pack(anchor='w')
        self.label(display.body, '默认使用圆点遮挡，账号管理与查询共用显示设置。', size=9, muted=True).pack(anchor='w', pady=(5, 12))
        ttk.Checkbutton(display.body, text='显示账号密码', variable=a.show_password_var, command=a._toggle_password_visibility, bootstyle='primary-round-toggle').pack(anchor='w')
        cleanup = Card(inner, height=154)
        cleanup.grid(row=3, column=1, sticky='nsew', pady=(0, 4))
        self.label(cleanup.body, '自动删除错误密码账号', bold=True).pack(anchor='w')
        hint = self.label(cleanup.body, '开启后在查询或登录时验证密码，仅自动删除 Steam 明确返回密码错误的账号。',
                          size=9, muted=True, justify='left')
        hint.pack(fill='x', pady=(5, 12))
        cleanup.body.bind('<Configure>', lambda e: hint.configure(wraplength=max(150, e.width)))
        a.auto_delete_wrong_password_button = ttk.Checkbutton(
            cleanup.body, text='自动删除错误密码账号', variable=a.auto_delete_wrong_password_var,
            command=a.save_auto_delete_wrong_password_setting, bootstyle='primary-round-toggle')
        a.auto_delete_wrong_password_button.pack(anchor='w')

    def _build_about(self):
        self.about = tk.Frame(self.content, bg=BG)
        card = Card(self.about, height=480, padding=24)
        card.pack(fill='x')
        self.label(card.body, 'PUBG账号管理系统', size=18, bold=True).pack(anchor='w')
        self.label(card.body, f'v{self.version}', muted=True).pack(anchor='w', pady=(6, 20))
        self.label(card.body, '使用方法', size=12, bold=True).pack(anchor='w', pady=(0, 12))
        guide = self.label(card.body, (
            '1. 导入账号：点击“粘贴导入”或“导入文件”，支持 CSV / JSON / TXT；纯文本使用“账号----密码”格式。\n\n'
            '2. 登录账号：选中一个账号后点击“一键登录”，也可双击账号或点击该行的“登录”按钮。\n\n'
            '3. 查询封禁：在设置中填写并保存 Steam Web API Key，再点击“查询封禁”。优先查询勾选账号，其次查询高亮账号；未选择时查询全部。可用“仅未查询”筛选待查询账号。\n\n'
            '4. 查看状态：“封禁”汇总游戏、社区或库存／经济封禁，不检测 VAC；“未查询”和“查询失败”不代表封禁。\n\n'
            '5. 账号清理：可在设置中开启“自动删除错误密码账号”，仅在 Steam 明确返回密码错误时删除。'
        ), muted=True, justify='left')
        guide.pack(fill='x')
        card.body.bind('<Configure>', lambda e: guide.configure(wraplength=max(200, e.width)))
        self.app.update_button = ActionButton(card.body, '检查更新', self.app.check_for_updates)
        self.app.update_button.pack(anchor='w', pady=(18, 0))

    def toggle_sidebar(self):
        self.expanded = not self.expanded
        self.sidebar.configure(width=184 if self.expanded else 54)
        for button in (self.menu_button, *self.nav_buttons.values()):
            button.expanded = self.expanded
            button.draw()

    def select_page(self, page):
        self.page = page
        self.account_footer.pack_forget()
        self.query_footer.pack_forget()
        footer = {'accounts': self.account_footer, 'query': self.query_footer}.get(page)
        if footer is not None:
            footer.pack(side='bottom', fill='x', pady=(16, 0), before=self.content)
        titles = {
            'accounts': ('PUBG 账号管理', '一键启动 Steam 快速登录 · 双击账号登录，右键编辑或删除'),
            'query': ('封禁查询', '使用账号库批量查询 Steam 公开封禁信息'),
            'settings': ('设置', ''),
            'about': ('关于', 'PUBG账号管理系统'),
        }
        self.title_var.set(titles[page][0])
        self.subtitle_var.set(titles[page][1])
        self.subtitle_label.pack_forget()
        if titles[page][1]:
            self.subtitle_label.pack(anchor='w', pady=(5, 0))
        for key, button in self.nav_buttons.items():
            button.selected = key == page
            button.draw()
        for widget in (self.list_area, self.settings, self.about):
            widget.pack_forget()
        if page in {'accounts', 'query'}:
            self.list_area.pack(fill='both', expand=True)
            self.account_toolbar.pack_forget()
            self.query_toolbar.pack_forget()
            toolbar = self.account_toolbar if page == 'accounts' else self.query_toolbar
            toolbar.pack(fill='x', pady=(0, 16), before=self.filters)
            a = self.app
            columns = ('pick', 'account_name', 'password', 'login_elapsed', 'pubg', 'row_actions')
            if page == 'query':
                columns = ('pick', 'account_name', 'password', 'query_status', 'pubg', 'login_elapsed', 'steam_id')
            for buttons in self.row_buttons.values():
                for button in buttons:
                    button.place_forget()
            a.tree.configure(displaycolumns=columns)
            self._fit_table_columns()
            a.query_progress_card.pack_forget()
            if page == 'query' and a.query_total:
                a.query_progress_card.pack(fill='x', pady=(0, 12), before=a.table_card)
        else:
            (self.settings if page == 'settings' else self.about).pack(fill='both', expand=True)
        self.refresh_query_selection()

    def refresh_account_totals(self):
        total, banned = self.app.store.account_totals()
        self.account_total_var.set(f'账号数量: {total}')
        self.banned_count_var.set(f'封禁账号: {banned}')

    def refresh_query_selection(self, _event=None):
        self.query_selected_var.set(f'当前选中: {len(self.app._selected_ids())} 个')

    def delete_row(self, account_id):
        a = self.app
        if str(a.delete_button['state']) == 'disabled':
            return
        previous_checked = set(a.checked_ids)
        previous_selected = a.tree.selection()
        a.checked_ids.clear()
        a.tree.selection_set(str(account_id))
        try:
            a.delete_selected()
        finally:
            a.checked_ids = previous_checked
            if a.store.connection.execute('SELECT 1 FROM accounts WHERE id=?', (account_id,)).fetchone() is None:
                a.checked_ids.discard(account_id)
            for item in a.tree.get_children():
                a.tree.set(item, 'pick', '■' if int(item) in a.checked_ids else '□')
            a._update_list_summary()
            a.tree.selection_set([item for item in previous_selected if a.tree.exists(item)])

    def _sync_row_actions(self):
        a = self.app
        active = set()
        active_buttons = set()
        if self.page in {'accounts', 'query'} and a.tree.winfo_ismapped():
            # Inspect only the visible rows, independent of the number of imported accounts.
            selected = set(a.tree.selection())
            visible = []
            for y in range(0, a.tree.winfo_height(), 10):
                item = a.tree.identify_row(y)
                if item and item not in visible:
                    visible.append(item)
            for item in visible:
                pick_box = a.tree.bbox(item, 'pick')
                if not pick_box:
                    continue
                active.add(item)
                if item not in self.row_checkboxes:
                    checkbox = SelectionCell(a.tree, lambda key=int(item): a._toggle_checked(key))
                    checkbox.bind('<MouseWheel>', self._scroll_over_cell)
                    self.row_checkboxes[item] = checkbox
                checkbox = self.row_checkboxes[item]
                tags = a.tree.item(item, 'tags')
                background = BLUE if item in selected else '#FFF0EE' if 'risk' in tags else '#FFF6E7' if 'failure' in tags else '#F3F9F4' if 'success' in tags else CARD
                checked = int(item) in a.checked_ids
                if checkbox.checked != checked or checkbox.cget('bg') != background:
                    checkbox.checked = checked
                    checkbox.configure(bg=background)
                    checkbox.draw()
                px, py, pw, ph = pick_box
                checkbox.place(x=px+(pw-24)//2, y=py+(ph-24)//2, width=24, height=24)
                if not checkbox.find_all():
                    checkbox.draw()
                if self.page != 'accounts':
                    continue
                box = a.tree.bbox(item, 'row_actions')
                if not box:
                    continue
                active_buttons.add(item)
                if item not in self.row_buttons:
                    login = ActionButton(a.tree, '登录', lambda key=int(item): a.open_steam_login(key), primary=True, width=86)
                    delete = ActionButton(a.tree, '删除', lambda key=int(item): self.delete_row(key), width=86)
                    self.row_buttons[item] = login, delete
                    for button in (login, delete):
                        button.bind('<MouseWheel>', self._scroll_over_cell)
                x, y, width, height = box
                half = width // 2
                for index, (button, source) in enumerate(zip(self.row_buttons[item], (a.steam_login_button, a.delete_button))):
                    if button.cget('bg') != background:
                        button.configure(bg=background)
                    if button['state'] != str(source['state']):
                        button.configure(state=str(source['state']))
                    button.place(x=x+index*half+6, y=y+5, width=half-12, height=height-10)
        for item in list(self.row_buttons):
            if item not in active_buttons:
                for button in self.row_buttons.pop(item):
                    button.destroy()
        for item in list(self.row_checkboxes):
            if item not in active:
                self.row_checkboxes.pop(item).destroy()
        for button, source in self.mirrors:
            if button['state'] != str(source['state']):
                button.configure(state=str(source['state']))
        self.root.after(120, self._sync_row_actions)

    def _scroll_over_cell(self, event):
        self.app.tree.yview_scroll(-int(event.delta / 120), 'units')
        self.app._queue_load_more()
        return 'break'
