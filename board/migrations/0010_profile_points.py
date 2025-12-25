from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("board", "0009_postimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="points",
            field=models.IntegerField(default=0),
        ),
    ]
