# Generated by Django 2.0.6 on 2019-02-13 13:17

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DiagnoseZhu',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='唯一主键')),
                ('pathology', models.CharField(blank=True, max_length=128, null=True, verbose_name='病理号')),
                ('his_diagnosis_label', models.CharField(blank=True, max_length=64, null=True, verbose_name='朱博士最新诊断标签')),
                ('is_delete', models.BooleanField(default=False, verbose_name='是否逻辑删除')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
            ],
            options={
                'verbose_name': '朱博士历史诊断标签',
                'verbose_name_plural': '朱博士历史诊断标签',
                'db_table': 'tb_diagnose_zhu',
            },
        ),
    ]