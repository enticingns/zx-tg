import json
from typing import Any

from zxtg.core.context import CallContext
from zxtg.core.kernel.enums import PluginType
from zxtg.core.kernel.manifest import Cmd, ConfigSpec, PluginManifest
from zxtg.core.services.config_service import config_service
from zxtg.core.services.gold_service import gold_service
from zxtg.core.services.item_service import item_service

DEFAULT_ITEMS = {
    "cookie": {
        "name": "曲奇饼干",
        "price": 50,
        "stock": 10,
        "status": True,
        "description": "美味的小饼干，恢复精力",
    },
    "potion": {
        "name": "好感药水",
        "price": 100,
        "stock": 5,
        "status": True,
        "description": "增加好感度的神秘药水",
    },
}

manifest = PluginManifest(
    key="shop",
    name="道具商店",
    version="1.0.0",
    author="ZX-TG Team",
    description="道具上架、下架、购买与库存管理",
    usage="发送 商店 查看道具；发送 购买 <道具ID> [数量]；发送 库存 <上架|下架|增加> <道具ID> [数量]",
    plugin_type=PluginType.NORMAL,
    menu_type="功能",
    level=0,
    configs=[
        ConfigSpec(
            key="SHOP_ITEMS",
            type="json",
            default=DEFAULT_ITEMS,
            help="商店道具列表配置",
        ),
    ],
    cmds=[
        Cmd(
            key="shop",
            pattern="商店",
            slash="shop",
            aliases=["商城"],
            help="查看商店道具列表",
        ),
        Cmd(
            key="buy",
            pattern="购买",
            slash="buy",
            aliases=["买"],
            help="购买商店道具: 购买 <道具ID> [数量]",
        ),
        Cmd(
            key="stock",
            pattern="库存",
            slash="stock",
            aliases=["商品管理"],
            help="管理道具库存: 库存 <上架|下架|增加> <道具ID> [数量]",
        ),
    ],
)


async def _get_shop_items(ctx: CallContext | None = None) -> dict[str, dict[str, Any]]:
    """Retrieve and normalize configured items (FR-BIP-03)."""
    items_raw = config_service.get("SHOP_ITEMS", plugin_key="shop")
    if items_raw is None and ctx is not None:
        items_raw = await ctx.config("SHOP_ITEMS")
    if isinstance(items_raw, str):
        try:
            items_raw = json.loads(items_raw)
        except Exception:
            items_raw = {}
    if not isinstance(items_raw, dict):
        items_raw = {}
    return {k: dict(v) for k, v in items_raw.items()}


async def _save_shop_items(items: dict[str, Any], ctx: CallContext | None = None) -> None:
    """Save modified item dictionary back to configuration and persist to DB."""
    await config_service.save_global("SHOP_ITEMS", items, plugin_key="shop")
    if ctx and ctx.plugin and "SHOP_ITEMS" in ctx.plugin.config:
        ctx.plugin.config["SHOP_ITEMS"] = items



async def handle_shop(ctx: CallContext) -> None:
    """List available items for purchase."""
    items = await _get_shop_items(ctx)
    available = {k: v for k, v in items.items() if v.get("status", True)}
    if not available:
        await ctx.reply("商店目前没有上架的商品。")
        return

    lines = ["🛒 **真寻小店 - 道具列表**\n"]
    for item_id, item in available.items():
        name = item.get("name", item_id)
        price = item.get("price", 0)
        stock = item.get("stock", 0)
        desc = item.get("description", "")
        desc_line = f"\n  说明：{desc}" if desc else ""
        lines.append(f"• `[{item_id}]` **{name}** - 💰 {price} 金币 | 库存: {stock}{desc_line}")

    lines.append("\n💡 购买命令：`购买 <道具ID> [数量]`（例如：`购买 cookie 1`）")
    await ctx.reply("\n".join(lines))


async def handle_buy(ctx: CallContext) -> None:
    """Handle atomic item purchase with rollback on failure (FR-BIP-03)."""
    args = ctx.event.command.args if ctx.event.command else []
    if not args:
        await ctx.reply("请指定要购买的道具ID，例如：购买 cookie 1")
        return

    item_id = args[0].lower().strip()
    count = 1
    if len(args) > 1:
        try:
            count = int(args[1])
        except ValueError:
            await ctx.reply("购买数量必须为正整数")
            return

    if count <= 0:
        await ctx.reply("购买数量必须大于0")
        return

    items = await _get_shop_items(ctx)
    if item_id not in items or not items[item_id].get("status", True):
        await ctx.reply(f"道具 '{item_id}' 不存在或已下架")
        return

    item = items[item_id]
    stock = item.get("stock", 0)
    if stock < count:
        await ctx.reply(f"库存不足：道具 '{item.get('name', item_id)}' 当前库存为 {stock}，所需数量为 {count}")
        return

    price = item.get("price", 0)
    total_cost = price * count
    user_gold = await gold_service.get_gold(ctx.user.id)
    if user_gold < total_cost:
        await ctx.reply(f"金币不足：购买需要 {total_cost} 金币，当前余额为 {user_gold}")
        return

    # Atomic Step 1: Deduct gold
    ok, msg = await gold_service.change_gold(ctx.user.id, -total_cost, reason=f"shop_buy:{item_id}")
    if not ok:
        await ctx.reply(f"扣除金币失败：{msg}")
        return

    # Atomic Step 2: Deduct stock
    item["stock"] -= count
    await _save_shop_items(items, ctx)

    # Atomic Step 3: Deliver item into UserItem inventory with rollback
    try:
        await item_service.add_item(user_id=ctx.user.id, item_id=item_id, count=count)
    except Exception as exc:
        # ROLLBACK: Refund gold, restore stock
        await gold_service.change_gold(ctx.user.id, total_cost, reason=f"shop_rollback:{item_id}")
        item["stock"] += count
        await _save_shop_items(items, ctx)
        await ctx.reply(f"道具发放异常，购买已回滚并退还金币: {exc}")
        return




    new_gold = await gold_service.get_gold(ctx.user.id)
    await ctx.reply(
        f"🎉 **购买成功！**\n"
        f"- 道具：{item.get('name', item_id)} × {count}\n"
        f"- 消耗金币：{total_cost}\n"
        f"- 剩余金币：{new_gold}\n"
        f"- 剩余库存：{item['stock']}"
    )


async def handle_stock(ctx: CallContext) -> None:
    """Handle item shelf status and stock updates (FR-BIP-03)."""
    if ctx.user.level < 10:
        await ctx.reply("权限不足：只有管理员或超级用户可管理商品库存与上下架")
        return

    args = ctx.event.command.args if ctx.event.command else []
    if len(args) < 2:
        await ctx.reply("格式错误，请使用：库存 <上架|下架|增加> <道具ID> [数量]")
        return

    action = args[0]
    item_id = args[1].lower().strip()
    items = await _get_shop_items(ctx)

    if item_id not in items:
        await ctx.reply(f"道具 '{item_id}' 不存在")
        return

    item_name = items[item_id].get("name", item_id)
    if action == "上架":
        items[item_id]["status"] = True
        await _save_shop_items(items, ctx)
        await ctx.reply(f"已上架道具 '{item_name}'")
    elif action == "下架":
        items[item_id]["status"] = False
        await _save_shop_items(items, ctx)
        await ctx.reply(f"已下架道具 '{item_name}'")
    elif action == "增加":
        if len(args) < 3:
            await ctx.reply("增加库存请指定数量，例如：库存 增加 cookie 5")
            return
        try:
            add_count = int(args[2])
        except ValueError:
            await ctx.reply("增加数量必须为整数")
            return
        items[item_id]["stock"] = items[item_id].get("stock", 0) + add_count
        await _save_shop_items(items, ctx)
        await ctx.reply(f"已为道具 '{item_name}' 增加库存 {add_count}，当前库存: {items[item_id]['stock']}")
    else:
        await ctx.reply("未知的库存动作，支持：上架、下架、增加")


async def setup(ctx: Any = None) -> None:
    """Optional lifecycle setup hook."""
    pass
