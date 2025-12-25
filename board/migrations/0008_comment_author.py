from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("board", "0007_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="author",
            field=models.CharField(default="?", max_length=20),
        ),
    ]
