from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, CharFilter
from rest_framework.filters import OrderingFilter, SearchFilter
from django.db import transaction
from django.db.models import F

import os
import time
import django_excel as excel
from djqscsv import render_to_csv_response
from collections import Counter
import xml.dom.minidom
from DMS.settings.dev import DATA_SAMBA_PREX, BATCH6_XMLS_PATH, BATCH6_1_XMLS_PATH, \
    BATCH6_CELLS_PATH, BATCH6_1_CELLS_PATH, BATCH6_2_CELLS_PATH, BATCH6_3_CELLS_PATH, BATCH6_3_XMLS_PATH

from Check.models import Check, CheckDetail
from Check.serializers import CheckSerializer

import logging
logger = logging.getLogger('django')


# import threading
# from dwebsocket.decorators import accept_websocket
# from django.shortcuts import render
#
# def base_view(request):
#     return render(request, 'test.html')
#
# clients = []
#
# @accept_websocket
# def echo(request):
#     if request.is_websocket:
#         lock = threading.RLock()
#         try:
#             lock.acquire()
#             clients.append(request.websocket)
#             for message in request.websocket:
#                 if not message:
#                     break
#                 for client in clients:
#                     client.send(message)
#         finally:
#             clients.remove(request.websocket)
#             lock.release()


class DownloadFile(APIView):
    """
    get: 导出审核版本数据训练详情csv/excel数据
    :parameter:
        type: 指定下载的格式, csv/xlsx/xls
    :example:
        /api/v1/checks/downloads/?type=csv
    """

    def get(self, request):

        suffix_name = request.GET.get('type', None)
        if not suffix_name:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'msg': '请求参数错误！'})

        if suffix_name not in ['csv', 'xlsx', 'xls']:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'msg': '仅支持下载csv和excel格式！'})

        # 通过指定字段的别名, 指定返回的格式顺序, 下载时默认按字母进行排序
        check_data = CheckDetail.objects.filter(is_delete=False).annotate(
            c1_审核版本号=F('check_version_number'), c2_大图名称=F('image'), c3_分类标签=F('classify'),
            c4_数量=F('class_number')).values('c1_审核版本号', 'c2_大图名称', 'c3_分类标签', 'c4_数量')

        # 命名返回文件名字(django-queryset-csv插件使用中文名字返回时会去掉, 使用英文则不会)
        file_name_add_date = 'ckeck_detail_' + time.strftime('%Y_%m_%d_%H_%M_%S') + '.{}'.format(suffix_name)

        # 返回对应格式的文件
        # 返回csv格式使用make_response_from_records会出现中文乱码,
        # pyexcel主要用于上传下载excel类型的数据,因此要改用其它框架django-queryset-csv
        if suffix_name == 'csv':
            # 指定返回字段的顺序
            field_name_list = sorted(list(check_data[0].keys()))
            return render_to_csv_response(check_data, filename=file_name_add_date, field_order=field_name_list)
        else:
            return excel.make_response_from_records(check_data, file_type=suffix_name, file_name=file_name_add_date)


class UpdateCheck(APIView):
    """
    post: 更新审核数据记录列表/详情信息
    :parameter:
        update_type: 指定更新审核版本列表还是详细列表, 可选值为：sample/detail
    :example:
        请求体中带上 {“update_type”: “sample”}
    """

    def post(self, request):

        start_time = time.time()

        # 获取请求体数据
        update_type = request.POST.get('update_type', None)
        if update_type not in ['sample', 'detail']:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'msg': '请求参数错误！'})

        # 存储所有XML/CELLS的版本号及路径
        version_list = [
            ('BATCH6', os.path.join(DATA_SAMBA_PREX, BATCH6_CELLS_PATH), os.path.join(DATA_SAMBA_PREX, BATCH6_XMLS_PATH)),
            ('BATCH6.1', os.path.join(DATA_SAMBA_PREX, BATCH6_1_CELLS_PATH), os.path.join(DATA_SAMBA_PREX, BATCH6_1_XMLS_PATH)),
            # ('BATCH6.2', os.path.join(DATA_SAMBA_PREX, BATCH6_2_CELLS_PATH), None),
            ('BATCH6.3', os.path.join(DATA_SAMBA_PREX, BATCH6_3_CELLS_PATH), os.path.join(DATA_SAMBA_PREX, BATCH6_3_XMLS_PATH))
        ]

        if update_type == 'sample':
            # 开启事务
            with transaction.atomic():
                # 创建保存点
                save_id = transaction.savepoint()

                try:
                    # 删除表中没有逻辑删除的记录,那些已逻辑删除的要保存记录下来
                    Check.objects.filter(is_delete=False).delete()

                    # 获取图像格式
                    for version_num, cells_version_path, xml_version_path in version_list:
                        # 存储该版本所有图像的后缀格式
                        suffx_list = []
                        # 细胞的存储路径
                        storage_path = cells_version_path.split('=')[2]
                        for file_name in os.listdir(xml_version_path):
                            # 获取文件对象
                            dom_obj = xml.dom.minidom.parse(os.path.join(xml_version_path, file_name))
                            # 获取元素对象
                            element_obj = dom_obj.documentElement

                            # 使用元素对象获取各个标签
                            # 通过Annotations标签获取大图全名(结果返回一个列表对象)
                            big_image_element_obj = element_obj.getElementsByTagName('Annotations')
                            # 获取属性值
                            # 获取大图的后缀格式并添加到列表中
                            image_full_name = big_image_element_obj[0].getAttribute('FullName')
                            suffx_list.append(os.path.splitext(image_full_name)[1])

                        # 图像格式
                        image_format_set = set(suffx_list)
                        image_format = ', '.join(image_format_set).replace('.', '')

                        # 所有图像列表
                        image_list = []
                        # 所有细胞分类列表
                        cells_classify_list = []
                        for cla in os.listdir(cells_version_path):
                            cla_full_path = os.path.join(cells_version_path, cla)
                            # 判断是否为文件夹(如果是其它文件如.zip等就跳过)
                            if os.path.isdir(cla_full_path):
                                for image in os.listdir(cla_full_path):
                                    image_list.append(image)
                                cells_classify_list.append(cla)

                        # 分类
                        classify = ', '.join(cells_classify_list)

                        # 创建一条记录
                        Check.objects.create(check_version_number=version_num, storage_path=storage_path,
                                             class_number=len(cells_classify_list), cells_number=len(image_list),
                                             image_format=image_format, classify=classify)

                    end_time = time.time()
                    cost_time = '%.2f' % (end_time - start_time)
                except Exception as e:
                    logger.error(e)
                    transaction.savepoint_rollback(save_id)
                    return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={'msg': '审核数据更新失败！'})

                # 提交事务
                transaction.savepoint_commit(save_id)

                return Response(status=status.HTTP_201_CREATED, data={'msg': '审核版本数据更新成功！', 'cost_time': cost_time})

        else:
            # 开启事务
            with transaction.atomic():
                # 创建保存点
                save_id = transaction.savepoint()

                try:
                    # 删除表中没有逻辑删除的记录,那些已逻辑删除的要保存记录下来
                    CheckDetail.objects.filter(is_delete=False).delete()

                    # 存储多条数据库数据对象
                    queryset_list = []
                    # 获取图像格式
                    for version_num, cells_version_path, xml_version_path in version_list:
                        for file_name in os.listdir(xml_version_path):
                            # 获取文件对象
                            dom_obj = xml.dom.minidom.parse(os.path.join(xml_version_path, file_name))
                            # 获取元素对象
                            element_obj = dom_obj.documentElement

                            # 使用元素对象获取各个标签
                            # 1.通过Annotations标签获取大图全名(结果返回一个列表对象)
                            big_image_element_obj = element_obj.getElementsByTagName('Annotations')
                            # 获取大图的名称
                            image_full_name = big_image_element_obj[0].getAttribute('FullName')
                            image_name = os.path.splitext(image_full_name)[0]

                            # 存储一张大图中所有的小图的分类
                            cells_type_list = []
                            # 2.通过Annotation标签获取所有小图(结果返回一个列表对象)
                            first_small_image_element_obj = element_obj.getElementsByTagName('Annotation')
                            # 遍历所有的小图, 获取的属性
                            for first_obj in first_small_image_element_obj:
                                # 获取Annotation下的Cell的标签对象
                                second_small_image_element_obj = first_obj.getElementsByTagName('Cell')
                                # 遍历Cell标签列表对象, 获取Cell中的属性值
                                for second_obj in second_small_image_element_obj:
                                    cells_type = second_obj.getAttribute('Type')
                                    cells_type_list.append(cells_type)

                            # 统计一张大图中, 每个类别的个数
                            cells_count_dict = dict(Counter(cells_type_list))
                            # TC17068105.kfb, HSIL_S, 12
                            # TC17068105.kfb, GEC, 56
                            # TC17068105.kfb, RC, 6
                            for k, v in cells_count_dict.items():
                                # 创建一条记录对象, 并添加到列表
                                queryset_list.append(
                                    CheckDetail(check_version_number=version_num,
                                                image=image_name, classify=k, class_number=v)
                                )

                    # 每次save()的时候都会访问一次数据库，导致性能问题。
                    # 使用django.db.models.query.QuerySet.bulk_create()批量创建对象，减少SQL查询次数
                    CheckDetail.objects.bulk_create(queryset_list)

                    end_time = time.time()
                    cost_time = '%.2f' % (end_time - start_time)
                except Exception as e:
                    logger.error(e)
                    transaction.savepoint_rollback(save_id)
                    return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={'msg': '审核版本详情数据更新失败！'})

                # 提交事务
                transaction.savepoint_commit(save_id)

                return Response(status=status.HTTP_201_CREATED, data={'msg': '审核版本详情数据更新成功！', 'cost_time': cost_time})


class CheckFilter(FilterSet):
    """搜索类"""

    check_version_number = CharFilter(lookup_expr='iexact')  # 模糊查询（包含），并且忽略大小写

    class Meta:
        model = Check
        fields = ['check_version_number']


class SCCheckView(ListCreateAPIView):
    """
    get: 查询审核数据记录列表
    post: 创建一条审核数据记录
    """

    # 指定查询集, 获取没有逻辑删除的数据
    queryset = Check.objects.filter(is_delete=False)

    # 指定序列化器
    serializer_class = CheckSerializer

    # OrderingFilter：指定排序的过滤器,可以按任意字段排序,通过在路由中通过ordering参数控制,如：?ordering=id
    # DjangoFilterBackend对应filter_fields属性，做相等查询
    # SearchFilter对应search_fields，对应模糊查询
    filter_backends = [OrderingFilter, DjangoFilterBackend, SearchFilter]
    # 默认指定按哪个字段进行排序
    ordering_fields = ('check_version_number', )
    # 指定可以被搜索字段
    filter_class = CheckFilter


class SUDCheckView(APIView):
    """
    get: 查询一条审核数据记录
    patch: 更新一条审核数据记录
    """

    def get(self, request, pk):
        # 根据id, 查询数据库对象
        try:
            diagnose = Check.objects.get(id=pk, is_delete=False)
        except Check.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={'msg': '数据不存在！'})

        # 序列化返回
        serializer = CheckSerializer(diagnose)
        return Response(serializer.data)

    def patch(self, request, pk):
        # 根据id, 查询数据库对象
        try:
            diagnose = Check.objects.get(id=pk, is_delete=False)
        except Check.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={'msg': '数据不存在！'})

        # 获取参数, 校验参数, 保存结果
        serializer = CheckSerializer(diagnose, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
