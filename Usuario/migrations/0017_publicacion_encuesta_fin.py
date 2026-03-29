from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Usuario', '0016_publicacion_encuesta_opciones_extra'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicacion',
            name='encuesta_fin',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
