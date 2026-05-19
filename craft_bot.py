"""
Droxen Crafting Kalkulátor - Discord Bot
A bot egy adott szobába kiküldi a craftolható tárgyakat,
kiválasztod, és kiírja mi kell hozzá.

Telepítés: pip install discord.py
"""

import discord
from discord.ext import commands
from discord import ui
import math


# ───────────────────────────────────────────────
#  CRAFT ADATOK
# ───────────────────────────────────────────────
ITEMS = {
    "fem":          {"name": "Fém",          "price": 1500},
    "rez":          {"name": "Réz",          "price": 1500},
    "alu":          {"name": "Alumínium",    "price": 1500},
    "csavar":       {"name": "Csavar",       "recipe": {"fem": 1,   "rez": 1,   "alu": 1}},
    "fegyvercso":   {"name": "Fegyvercső",   "recipe": {"fem": 0.5, "rez": 1.3, "alu": 1}},
    "fegyverdarab": {"name": "Fegyverdarab", "recipe": {"fem": 1.5, "rez": 1.2, "alu": 1}},
    "hx_pisztoly":  {
        "name": "M13 Faith",
        "isTarget": True,
        "recipe": {"csavar": 45, "fegyvercso": 15, "fegyverdarab": 15},
    },
}

TARGET_ITEMS = {k: v for k, v in ITEMS.items() if v.get("isTarget")}


# ───────────────────────────────────────────────
#  LOGIKA
# ───────────────────────────────────────────────
def get_requirements(item_id, amount, inventory=None, result=None):
    if inventory is None:
        inventory = {}
    if result is None:
        result = {"raw": {}, "crafts": {}}
    if amount <= 0:
        return result

    available = inventory.get(item_id, 0)
    if available >= amount - 1e-6:
        inventory[item_id] = available - amount
        return result

    needed = amount - available
    item = ITEMS.get(item_id)

    if not item or "recipe" not in item:
        inventory[item_id] = 0
        result["raw"][item_id] = result["raw"].get(item_id, 0) + needed
        return result

    if not item.get("isTarget"):
        craft_amount = math.ceil(needed / 10) * 10
        inventory[item_id] = craft_amount - needed
    else:
        craft_amount = needed
        inventory[item_id] = 0

    result["crafts"][item_id] = result["crafts"].get(item_id, 0) + craft_amount

    for ing_id, qty in item["recipe"].items():
        get_requirements(ing_id, qty * craft_amount, inventory, result)

    return result


def fmt(n):
    return f"{n:,.0f}".replace(",", " ")


def build_result_embed(target_id, mennyiseg):
    reqs = get_requirements(target_id, mennyiseg)
    item_name = ITEMS[target_id]["name"]

    embed = discord.Embed(
        title=f"⚙️  {item_name}  ×{mennyiseg}",
        color=0x00D2FF,
    )

    # Köztes craftok
    crafts_text = ""
    for cid, camount in reqs["crafts"].items():
        if cid == target_id or camount < 0.001:
            continue
        sub = "".join(
            f"\n　↳ {ITEMS[ing]['name']}: **{qty * camount:g} db**"
            for ing, qty in ITEMS[cid]["recipe"].items()
        )
        crafts_text += f"⚙️ **{ITEMS[cid]['name']}** — {camount:g} db{sub}\n"

    embed.add_field(
        name="🔩 Köztes craftok",
        value=crafts_text.strip() or "*Nincs szükség köztes craftolásra.*",
        inline=False,
    )

    # Nyersanyagok
    raw_text = ""
    total_cost = 0
    for rid, ramount in reqs["raw"].items():
        if ramount < 0.001:
            continue
        rdata = ITEMS[rid]
        amt = round(ramount, 2)
        if "price" in rdata:
            cost = rdata["price"] * ramount
            total_cost += cost
            raw_text += f"🧱 **{rdata['name']}**: {amt:g} db — _{fmt(cost)} $_\n"
        else:
            raw_text += f"🧱 **{rdata['name']}**: {amt:g} db\n"

    embed.add_field(
        name="📦 Szükséges nyersanyagok",
        value=raw_text.strip() or "✅ Minden megvan!",
        inline=False,
    )
    embed.add_field(name="💰 Becsült ár", value=f"**{fmt(total_cost)} $**", inline=False)
    embed.set_footer(text="Droxen Crafting Kalkulátor • by Roka  |  Csak te látod ezt az üzenetet")
    return embed


# ───────────────────────────────────────────────
#  UI — Mennyiség modal
# ───────────────────────────────────────────────
class QtyModal(ui.Modal, title="Mennyiség megadása"):
    mennyiseg = ui.TextInput(
        label="Hány darabot szeretnél craftolni?",
        placeholder="pl. 1",
        default="1",
        min_length=1,
        max_length=6,
    )

    def __init__(self, target_id):
        super().__init__()
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.mennyiseg.value)
            if qty < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Érvénytelen szám!", ephemeral=True)
            return

        embed = build_result_embed(self.target_id, qty)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ───────────────────────────────────────────────
#  UI — Tárgy választó dropdown
# ───────────────────────────────────────────────
class CraftSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=v["name"], value=k, emoji="⚙️")
            for k, v in TARGET_ITEMS.items()
        ]
        super().__init__(
            placeholder="🔧  Válaszd ki, mit akarsz craftolni...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(QtyModal(self.values[0]))


class CraftView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)   # sosem jár le
        self.add_item(CraftSelect())


# ───────────────────────────────────────────────
#  BOT
# ───────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


async def send_craft_menu(channel):
    """Kiküldi (vagy frissíti) a craft menüt a megadott csatornába."""
    # Korábbi bot-üzenetek törlése hogy ne halmozódjon
    async for msg in channel.history(limit=30):
        if msg.author == bot.user:
            await msg.delete()

    embed = discord.Embed(
        title="🔧 Droxen Crafting Kalkulátor",
        description=(
            "Válaszd ki az alábbi listából, **mit szeretnél craftolni**.\n"
            "Ezután megadhatod a kívánt mennyiséget, "
            "és a bot kiszámolja, mi szükséges hozzá.\n\n"
            "> Az eredményt csak **te** látod."
        ),
        color=0xFF0000,
    )
    embed.set_footer(text="by Roka")
    await channel.send(embed=embed, view=CraftView())


@bot.event
async def on_ready():
    # Persistent view regisztrálása (bot újraindítás után is működjön)
    bot.add_view(CraftView())
    await bot.tree.sync()
    print(f"✅ Bot online: {bot.user}")

    channel = bot.get_channel(CRAFT_CHANNEL_ID)
    if channel is None:
        print(f"❌ Csatorna nem található (ID: {CRAFT_CHANNEL_ID}). Ellenőrizd a CRAFT_CHANNEL_ID értékét!")
        return

    await send_craft_menu(channel)
    print(f"📨 Craft menü elküldve → #{channel.name}")


# !craftmenu — manuálisan újraküldi az aktuális csatornába (csak admin)
@bot.command(name="craftmenu")
@commands.has_permissions(manage_messages=True)
async def craftmenu_cmd(ctx):
    await send_craft_menu(ctx.channel)
    try:
        await ctx.message.delete()
    except Exception:
        pass


bot.run(BOT_TOKEN)
