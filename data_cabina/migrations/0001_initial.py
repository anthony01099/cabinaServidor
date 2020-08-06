# Generated by Django 3.1 on 2020-08-06 15:54

import data_cabina.utils
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Cabin',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='CabinToken',
            fields=[
                ('id', models.CharField(default=data_cabina.utils.generate_token, editable=False, max_length=40, primary_key=True, serialize=False)),
                ('is_used', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=20)),
                ('description', models.TextField()),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Setting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('save_images', models.BooleanField(default=False)),
                ('company', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='data_cabina.company')),
            ],
        ),
        migrations.CreateModel(
            name='Capture',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('temp', models.FloatField()),
                ('is_wearing_mask', models.BooleanField(default=False)),
                ('is_image_saved', models.BooleanField(default=False)),
                ('image', models.FileField(blank=True, null=True, upload_to=data_cabina.utils.media_upload_to)),
                ('cabin', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='data_cabina.cabin')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='cabin',
            name='company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data_cabina.company'),
        ),
        migrations.AddField(
            model_name='cabin',
            name='token',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data_cabina.cabintoken'),
        ),
    ]
