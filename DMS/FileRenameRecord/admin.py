from django.contrib import admin
from . import models
# Register your models here.


@admin.register(models.FileRenameRecord)
class FileRenameRecordAdmin(admin.ModelAdmin):

    # ------ 列表页的显示 ------- #

    # 定义函数，获取一对一/一对多关键表中的某个值
    # def get_pathology(self, obj):
    #     """获取病理号"""
    #     return obj.image_info_file.pathology

    # 在文章列表页面显示的字段, 不是详情里面的字段
    # 将show_tags函指定到列表中即可显示多对多字段的结果!!
    list_display = ['id', 'pathology', 'current_file_name', 'his_name1', 'his_name2',
                    'his_name3', 'his_name4', 'his_name5', 'create_time', 'update_time']

    # 设置哪些字段可以点击进入编辑界面
    list_display_links = ('id', 'pathology')

    # 每页显示10条记录
    list_per_page = 10

    # 搜索栏
    search_fields = ['pathology', 'current_file_name', 'his_name1']
