from django.core.management.base import BaseCommand

from packages.models import Package


class Command(BaseCommand):
    help = "Seed the database with default service packages."

    PACKAGES = [
        {
            "name": "Starter",
            "description": "Great for individuals just getting started with AI transcription.",
            "max_transcriptions": 10,
            "max_file_size_mb": 50,
            "is_active": True,
        },
        {
            "name": "Professional",
            "description": "For professionals with regular transcription needs.",
            "max_transcriptions": 50,
            "max_file_size_mb": 200,
            "is_active": True,
        },
        {
            "name": "Business",
            "description": "High-volume package for businesses and teams.",
            "max_transcriptions": 200,
            "max_file_size_mb": 500,
            "is_active": True,
        },
        {
            "name": "Unlimited",
            "description": "No limits — perfect for power users and enterprise customers.",
            "max_transcriptions": -1,  # -1 = unlimited
            "max_file_size_mb": -1,    # -1 = unlimited
            "is_active": True,
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding service packages…"))
        created = 0
        skipped = 0

        for data in self.PACKAGES:
            obj, is_new = Package.objects.get_or_create(
                name=data["name"],
                defaults=data,
            )
            if is_new:
                created += 1
                limit = "Unlimited" if data["max_transcriptions"] == -1 else str(data["max_transcriptions"])
                self.stdout.write(
                    self.style.SUCCESS(f"  [+] {obj.name} ({limit} transcriptions)")
                )
            else:
                skipped += 1
                self.stdout.write(f"  [=] {obj.name} (already exists, skipped)")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} package(s) created, {skipped} already existed."
            )
        )
