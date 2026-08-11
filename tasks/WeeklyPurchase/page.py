from tasks.GameUi.default_pages import page_shirin
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.WeeklyPurchase.assets import WeeklyPurchaseAssets

page_guild_store = Page(WeeklyPurchaseAssets.I_RM_CHECK_GUILD_STORE, priority=75, category='guild')
page_guild_store.connect(page_shirin, GlobalGameAssets.I_UI_BACK_RED, key="page_guild_store->page_shirin")
page_shirin.connect(page_guild_store, WeeklyPurchaseAssets.I_GUILD_STORE, key="page_shirin->page_guild_store")
