# This historical migration records the database change identified as
# 0014_seed_capacity_packages_and_experiences.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

from decimal import Decimal

from django.db import migrations


# This forward migration prepares the historical records required by this release while preserving
# existing customised data where the migration allows it.
def seed_capacity_packages_and_experiences(apps, schema_editor):
    """Add the new public catalogue without changing historical bookings."""

    Category = apps.get_model("party_builder", "Category")
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    AddonExperience = apps.get_model("party_builder", "AddonExperience")

    party_packages, _ = Category.objects.get_or_create(
        slug="party-packages",
        defaults={
            "name": "Party Packages",
            "description": "Capacity-based starting packages for Popadoo celebrations.",
            "display_order": 10,
            "is_active": True,
        },
    )

    category_specs = [
        ("Entertainment", "entertainment", None, 20),
        ("Shows and characters", "shows-and-characters", "entertainment", 21),
        ("Games and adventures", "games-and-adventures", "entertainment", 22),
        ("Music and dance", "music-and-dance", "entertainment", 23),
        ("Creative Activities", "creative-activities", None, 30),
        ("Arts and crafts", "arts-and-crafts", "creative-activities", 31),
        ("Face and body art", "face-and-body-art", "creative-activities", 32),
        ("Science and sensory", "science-and-sensory", "creative-activities", 33),
        ("Celebration Extras", "celebration-extras", None, 40),
        ("Decorations", "decorations", "celebration-extras", 41),
        ("Photos and keepsakes", "photos-and-keepsakes", "celebration-extras", 42),
        ("Food activities", "food-activities", "celebration-extras", 43),
    ]
    categories = {}
    for name, slug, parent_slug, display_order in category_specs:
        parent = categories.get(parent_slug)
        category, _ = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "parent": parent,
                "description": f"{name} ideas for a customised children’s party.",
                "display_order": display_order,
                "is_active": True,
            },
        )
        categories[slug] = category

    package_specs = [
        {
            "name": "Basic Popadoo Party",
            "slug": "basic-popadoo-party",
            "capacity": 10,
            "price": "180.00",
            "duration": 120,
            "order": 10,
            "description": "A friendly two-hour starting package for smaller celebrations, ready to personalise with optional experiences.",
            "included": "Party host\nMusic and organised games\nBasic party setup",
        },
        {
            "name": "Popadoo Plus Party",
            "slug": "popadoo-plus-party",
            "capacity": 15,
            "price": "255.00",
            "duration": 120,
            "order": 20,
            "description": "A flexible two-hour package for up to 15 children with extra coordination for a slightly bigger group.",
            "included": "Party host\nMusic and organised games\nExpanded party setup",
        },
        {
            "name": "Popadoo Classic Party",
            "slug": "popadoo-classic-party",
            "capacity": 20,
            "price": "330.00",
            "duration": 150,
            "order": 30,
            "description": "A balanced two-and-a-half-hour package for up to 20 children, with room to add creative or performance experiences.",
            "included": "Party host\nMusic and organised games\nClassic party setup\nActivity coordination",
        },
        {
            "name": "Popadoo Big Party",
            "slug": "popadoo-big-party",
            "capacity": 25,
            "price": "400.00",
            "duration": 150,
            "order": 40,
            "description": "A larger-group starting package for up to 25 children with additional planning support and flexible add-ons.",
            "included": "Lead party host\nMusic and organised games\nLarge-group setup\nActivity coordination",
        },
        {
            "name": "Popadoo XL Party",
            "slug": "popadoo-xl-party",
            "capacity": 30,
            "price": "465.00",
            "duration": 180,
            "order": 50,
            "description": "A three-hour package for up to 30 children, designed for busy celebrations that need more time and coordination.",
            "included": "Lead party host\nAssistant coordination\nMusic and organised games\nXL party setup",
        },
        {
            "name": "Popadoo Mega Party",
            "slug": "popadoo-mega-party",
            "capacity": 35,
            "price": "525.00",
            "duration": 180,
            "order": 60,
            "description": "A three-hour package for up to 35 children with enhanced staffing support and plenty of space for optional experiences.",
            "included": "Lead party host\nAssistant coordination\nMusic and large-group games\nMega party setup",
        },
        {
            "name": "Popadoo Super Party",
            "slug": "popadoo-super-party",
            "capacity": 40,
            "price": "580.00",
            "duration": 210,
            "order": 70,
            "description": "A three-and-a-half-hour package for up to 40 children, built for high-energy celebrations with stronger coordination.",
            "included": "Lead party host\nTwo-person coordination team\nMusic and large-group games\nSuper party setup",
        },
        {
            "name": "Popadoo Festival Party",
            "slug": "popadoo-festival-party",
            "capacity": 50,
            "price": "680.00",
            "duration": 240,
            "order": 80,
            "description": "A four-hour festival-style package for up to 50 children with the most planning support and room for multiple experiences.",
            "included": "Lead party host\nExpanded coordination team\nMusic and large-group games\nFestival-style setup",
        },
    ]

    PartyPackage.objects.filter(is_default=True).update(is_default=False)
    for spec in package_specs:
        package, created = PartyPackage.objects.get_or_create(
            slug=spec["slug"],
            defaults={
                "name": spec["name"],
                "category": party_packages,
                "short_description": spec["description"],
                "base_price": Decimal(spec["price"]),
                "duration_minutes": spec["duration"],
                "included_guest_count": spec["capacity"],
                "included_experiences": spec["included"],
                "is_default": False,
                "is_active": True,
                "display_order": spec["order"],
            },
        )
        if spec["slug"] == "basic-popadoo-party":
            # The original seed record already has these values. Only fill fields
            # that still match the old catalogue shape so custom edits survive.
            changed = []
            if package.category_id != party_packages.pk:
                package.category = party_packages
                changed.append("category")
            if package.included_guest_count == 10 and package.base_price == Decimal("180.00"):
                package.duration_minutes = spec["duration"]
                package.display_order = spec["order"]
                changed.extend(["duration_minutes", "display_order"])
            package.is_default = True
            package.is_active = True
            changed.extend(["is_default", "is_active"])
            package.save(update_fields=sorted(set(changed)))

    addon_specs = [
        ("Face Painting", "face-painting", "face-and-body-art"),
        ("Balloon Modelling", "balloon-modelling", "arts-and-crafts"),
        ("Treasure Hunt", "treasure-hunt", "games-and-adventures"),
        ("Creative Craft Workshop", "creative-craft-workshop", "arts-and-crafts"),
        ("Mini Magic Show", "mini-magic-show", "shows-and-characters"),
        ("Themed Balloon Decoration", "themed-balloon-decoration", "decorations"),
        ("Extra Entertainer", "extra-entertainer", "shows-and-characters"),
        ("Party Favour Pack", "party-favour-pack", "photos-and-keepsakes"),
        ("Bubble Show", "bubble-show", "90.00", 30, "◯", True, "shows-and-characters", "A playful bubble performance with giant bubbles and interactive moments.", 90),
        ("Kids Disco and Dance Games", "kids-disco-dance-games", "75.00", 45, "♫", True, "music-and-dance", "Music, movement and guided dance games for an energetic party group.", 100),
        ("Slime Laboratory", "slime-laboratory", "95.00", 45, "✦", True, "science-and-sensory", "A supervised slime-making activity with colourful, child-friendly materials.", 110),
        ("Junior Science Experiments", "junior-science-experiments", "120.00", 45, "⚗", True, "science-and-sensory", "Simple hands-on science demonstrations adapted for young party guests.", 120),
        ("Character Visit", "character-visit", "130.00", 30, "★", True, "shows-and-characters", "A themed character arrives for greetings, photos and a short activity.", 130),
        ("Superhero Training", "superhero-training", "100.00", 45, "⚡", False, "games-and-adventures", "Team challenges and movement games styled as a fun superhero training session.", 140),
        ("Puppet Show", "puppet-show", "110.00", 40, "♬", False, "shows-and-characters", "A compact puppet performance with age-appropriate stories and audience participation.", 150),
        ("Karaoke Party", "karaoke-party", "85.00", 45, "♪", False, "music-and-dance", "A guided karaoke session with children’s favourites and group sing-alongs.", 160),
        ("Party Photo Booth", "party-photo-booth", "120.00", 0, "▣", True, "photos-and-keepsakes", "A themed photo area with playful props for party keepsakes.", 170),
        ("Glitter Tattoos", "glitter-tattoos", "70.00", 0, "✧", False, "face-and-body-art", "Temporary glitter designs applied with child-friendly cosmetic materials.", 180),
        ("Cupcake Decorating", "cupcake-decorating", "100.00", 45, "♨", False, "food-activities", "Children decorate cupcakes with colourful toppings in a guided activity.", 190),
        ("Piñata Game", "pinata-game", "65.00", 20, "◆", False, "games-and-adventures", "A supervised party game with turn-taking and a celebratory prize reveal.", 200),
    ]

    generic_experiences = Category.objects.filter(slug="experiences").first()
    for entry in addon_specs:
        if len(entry) == 3:
            name, slug, category_slug = entry
            addon = AddonExperience.objects.filter(slug=slug).first()
            if addon and (generic_experiences is None or addon.category_id == generic_experiences.pk):
                addon.category = categories[category_slug]
                addon.save(update_fields=["category"])
            continue
        name, slug, price, duration, icon, featured, category_slug, description, order = entry
        AddonExperience.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": categories[category_slug],
                "short_description": description,
                "price": Decimal(price),
                "duration_minutes": duration,
                "icon": icon,
                "is_featured": featured,
                "is_active": True,
                "display_order": order,
            },
        )


# This migration helper performs the data part of the historical change recorded in this file.
def keep_catalogue_on_reverse(apps, schema_editor):
    """Catalogue records may be referenced by bookings, so reversal is a safe no-op."""


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [("party_builder", "0013_testimonial_visibility")]
    operations = [
        migrations.RunPython(
            seed_capacity_packages_and_experiences,
            keep_catalogue_on_reverse,
        )
    ]
