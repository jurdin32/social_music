from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Usuario', '0015_publicacion_encuesta_opcion1_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicacion',
            name='encuesta_opciones_extra',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
