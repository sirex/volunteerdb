# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-01-01 21:32
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_place'),
    ]

    operations = [
        migrations.AlterField(
            model_name='place',
            name='population',
            field=models.IntegerField(null=True),
        ),
    ]
