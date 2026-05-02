# Download this file as a .txt file
# and attach the file along with the installer eval provided

import discord
from asgiref.sync import sync_to_async

async def rarity_callback(interaction, reverse: bool = False, search: str = None, ephemeral: bool = False):

    from ballsdex.settings import settings
    from collections import defaultdict

    MAX_DESC = 4000

    def safe(text):
        return text if len(text) <= MAX_DESC else text[:MAX_DESC - 10] + "\n..."

    try:
        try:
            balls = await Ball.all()
        except:
            balls = await sync_to_async(list)(Ball.objects.all())

        enabled = [b for b in balls if getattr(b, "enabled", True)]
        name = settings.collectible_name.capitalize()
        plural = settings.plural_collectible_name.capitalize()

        # ================= SEARCH =================
        if search:
            try:
                rarity_value = float(search.replace(",", "."))
                matches = [b for b in enabled if float(b.rarity) == rarity_value]

                if not matches:
                    return await interaction.response.send_message(
                        f"No {plural} found with rarity `{search}`.",
                        ephemeral=True
                    )

                lines = []
                for b in matches:
                    emoji = bot.get_emoji(getattr(b, "emoji_id", None))
                    emoji = str(emoji) if emoji else "N/A"
                    lines.append(f"⋄ {emoji} {b.country}")

                return await interaction.response.send_message(
                    safe(f"{plural} with rarity `{search}`:\n" + "\n".join(lines)),
                    ephemeral=True
                )

            except:
                pass

            ball = next((b for b in enabled if b.country.lower() == search.lower()), None)

            if not ball:
                return await interaction.response.send_message(
                    f"The {name.lower()} could not be found.",
                    ephemeral=True
                )

            emoji = bot.get_emoji(getattr(ball, "emoji_id", None))
            emoji = str(emoji) if emoji else "N/A"

            return await interaction.response.send_message(
                f"{emoji} **{ball.country}**\nRarity: `{ball.rarity}`",
                ephemeral=True
            )

        # ================= PAGINATION =================
        await interaction.response.defer(ephemeral=ephemeral)

        rarity_map = defaultdict(list)
        for b in enabled:
            rarity_map[b.rarity].append(b)

        sorted_rarities = sorted(rarity_map.keys(), reverse=reverse)

        entries = []
        for rarity in sorted_rarities:
            lines = []
            for b in rarity_map[rarity]:
                emoji = bot.get_emoji(getattr(b, "emoji_id", None))
                emoji = str(emoji) if emoji else "N/A"
                lines.append(f"⋄ {emoji} {b.country}")
            entries.append(f"**Rarity: {rarity}**\n" + "\n".join(lines))

        per_page = 5
        pages = [
            safe("\n\n".join(entries[i:i + per_page]))
            for i in range(0, len(entries), per_page)
        ]

        def make_embed(i):
            return discord.Embed(
                title=f"{plural} Rarity List",
                description=pages[i],
                color=0x40E0D0
            ).set_footer(text=f"Page {i+1}/{len(pages)}")

        # ================= MODAL =================
        class PageModal(discord.ui.Modal, title="Go to Page"):
            page_input = discord.ui.TextInput(
                label="Page number",
                placeholder=f"Enter a number between 1 and {len(pages)}",
                required=True
            )

            async def on_submit(self, inter: discord.Interaction):
                if not self.page_input.value.isdigit():
                    return await inter.response.send_message("Only numbers allowed.", ephemeral=True)

                page = int(self.page_input.value)
                if not (1 <= page <= len(pages)):
                    return await inter.response.send_message(
                        f"Expected 1 - {len(pages)}",
                        ephemeral=True
                    )

                nv = create_view(page - 1)
                nv.message = inter.message
                await inter.response.edit_message(embed=make_embed(page - 1), view=nv)

        # ================= VIEW =================
        def create_view(page):

            class V(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=180)
                    self.page = page
                    self.owner = interaction.user.id

                async def interaction_check(self, inter):
                    if inter.user.id != self.owner:
                        await inter.response.send_message(
                            "This pagination menu cannot be controlled by you, sorry!",
                            ephemeral=True
                        )
                        return False
                    return True

                async def on_timeout(self):
                    for c in self.children:
                        c.disabled = True
                    try:
                        await self.message.edit(view=self)
                    except:
                        pass

            v = V()

            def go(p):
                async def inner(inter):
                    nv = create_view(p)
                    nv.message = inter.message
                    await inter.response.edit_message(embed=make_embed(p), view=nv)
                return inner

            # FIRST
            v.add_item(discord.ui.Button(label="≪", disabled=(page == 0)))
            v.children[-1].callback = go(0)

            # PREVIOUS
            v.add_item(discord.ui.Button(
                label=str(page) if page > 0 else "…",
                style=discord.ButtonStyle.blurple,
                disabled=(page == 0)
            ))
            v.children[-1].callback = go(page - 1)

            # CURRENT
            v.add_item(discord.ui.Button(label=str(page + 1), disabled=True))

            # NEXT
            v.add_item(discord.ui.Button(
                label=str(page + 2) if page < len(pages) - 1 else "…",
                style=discord.ButtonStyle.blurple,
                disabled=(page >= len(pages) - 1)
            ))
            v.children[-1].callback = go(page + 1)

            # LAST
            v.add_item(discord.ui.Button(label="≫", disabled=(page >= len(pages) - 1)))
            v.children[-1].callback = go(len(pages) - 1)

            # SKIP
            async def skip(inter):
                await inter.response.send_modal(PageModal())

            v.add_item(discord.ui.Button(label="Skip to page..."))
            v.children[-1].callback = skip

            # QUIT
            async def quit_btn(inter):
                for c in v.children:
                    c.disabled = True
                await inter.response.edit_message(view=v)

            v.add_item(discord.ui.Button(label="Quit", style=discord.ButtonStyle.red))
            v.children[-1].callback = quit_btn

            return v

        view = create_view(0)

        msg = await interaction.followup.send(
            embed=make_embed(0),
            view=view,
            ephemeral=ephemeral
        )

        view.message = msg

    except Exception as e:
        try:
            await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
        except:
            pass
