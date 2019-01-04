from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from django.db.models import Count
from django.db import transaction

import os
import time
import pandas as pd
from sqlalchemy import create_engine
import django_excel as excel
from DMS.utils.uploads import save_upload_file

from Case.models import Case
from Case.serializers import CaseSerializer


class UploadFile(APIView):
    """
    post: 上传csv/excel格式的数据
    """

    def post(self, request):

        # 获取上传的文件, 'file'值是前端页面input框的name属性的值
        _file = request.FILES.get('file', None)
        # 如果获取不到内容, 则说明上传失败
        if not _file:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"msg": '文件上传失败！'})

        # ---------- 保存上传文件 ---------- #

        # 获取文件的后缀名, 判断上传文件是否符合格式要求
        suffix_name = os.path.splitext(_file.name)[1]
        if suffix_name not in ['.csv', '.xls', '.xlsx']:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"msg": '请上传csv或excel格式的文件！'})

        upload_file_rename = save_upload_file(_file)
        # ---------- 读取上传文件数据 ---------- #
        # excel格式
        if suffix_name in ['.xls', '.xlsx']:
            data = pd.read_excel(upload_file_rename)
        # csv格式
        else:
            data = pd.read_csv(upload_file_rename)

        # 自定义列名
        # 重新定义表中字段的列名, 因为插入数据库时，时按表中的字段对应一一插入到数据库中的，因此列名要与数据库中保持一致
        column_name = ['pathology', 'diagnosis_label_doctor', 'waveplate_source', 'making_way', 'check_date',
                       'diagnosis_date', 'last_menstruation', 'clinical_observed']
        data.columns = column_name

        # 保存到数据库前, 手动添加is_delete列与时间列, 以及对诊断标签进行处理
        data['is_delete'] = False
        data['create_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
        data['update_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
        data['diagnosis_label_doctor_filter'] = data.diagnosis_label_doctor.str.extract(r'(\w+)')

        # ----------- 保存结果到数据库 ----------- #
        # 开启事务
        with transaction.atomic():
            # 创建保存点
            save_id = transaction.savepoint()

            try:
                # 删除表中没有逻辑删除的记录,那些已逻辑删除的要保存记录下来
                Case.objects.filter(is_delete=False).delete()

                # 将数据写入mysql的数据库，但需要先通过sqlalchemy.create_engine建立连接,且字符编码设置为utf8，否则有些latin字符不能处理
                con = create_engine('mysql+mysqldb://root:kyfq@localhost:3306/dms?charset=utf8')
                # chunksize:
                # 如果data的数据量太大，数据库无法响应可能会报错，这时候就可以设置chunksize，比如chunksize = 1000，data就会一次1000的循环写入数据库。
                # if_exists:
                # 如果表中有数据，则追加
                # index:
                # index=False，则不将dataframe中的index列保存到数据库
                data.to_sql('tb_case_info', con, if_exists='append', index=False, chunksize=1000)
            except Exception as e:
                transaction.savepoint_rollback(save_id)
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"msg": '导入数据库失败！'})

            # 提交事务
            transaction.savepoint_commit(save_id)

            # 写入image表后，再同步写入更名记录表以及朱博士诊断表????
            return Response(status=status.HTTP_201_CREATED, data={"msg": '上传成功！'})


class DownloadFile(APIView):
    """
    get: 导出csv/excel数据
    :parameter:
        type: 指定下载的格式, csv/xlsx/xls
    :example:
        /api/v1/cases/downloads/?type=csv
    """

    def get(self, request):

        suffix_name = request.GET.get('type', None)
        if not suffix_name:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'msg': '请求参数错误！'})

        if suffix_name not in ['csv', 'xlsx', 'xls']:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'msg': '仅支持下载csv和excel格式！'})

        img_data = Case.objects.values('pathology', 'diagnosis_label_doctor', 'waveplate_source', 'making_way',
                                       'check_date', 'diagnosis_date', 'last_menstruation', 'clinical_observed')

        # 返回对应格式的文件
        return excel.make_response_from_records(img_data, file_type=suffix_name, file_name='大图信息')


class FindDuplicateFileName(APIView):
    """
    get: 查找病例中出现重复的病理号及重复的次数
    """

    def get(self, request):
        # 查询病理号出现的次数大于1的记录
        dup_file_name = Case.objects.filter(is_delete=False).values('pathology').annotate(
            dup_count=Count('pathology')).filter(dup_count__gt=1)
        # 转换成列表
        dup_file_name_list = list(dup_file_name)

        # ----- 返回结果 ------ #
        result_dict = {
            "dup_file_name": dup_file_name_list
        }
        return Response(status=status.HTTP_200_OK, data=result_dict)


class SCCaseView(ListCreateAPIView):
    """
    get: 查询病例记录列表
    post: 新增一条病例记录
    """

    # 指定查询集, 获取没有逻辑删除的数据
    queryset = Case.objects.filter(is_delete=False)

    # 指定序列化器
    serializer_class = CaseSerializer

    # OrderingFilter：指定排序的过滤器,可以按任意字段排序,通过在路由中通过ordering参数控制,如：?ordering=id
    # DjangoFilterBackend对应filter_fields属性，做相等查询
    # SearchFilter对应search_fields，对应模糊查询
    filter_backends = [OrderingFilter, DjangoFilterBackend, SearchFilter]
    # 默认指定按哪个字段进行排序
    ordering = ('pathology',)
    # 指定可以被搜索字段, 如在路由中通过?id=2查询id为2的记录
    filter_fields = ('id', 'diagnosis_label_doctor')


class SUDCaseView(APIView):
    """
    get: 查询一条病例记录
    delete: 删除一条病例数据
    """

    def get(self, request, pk):
        # 根据id, 查询数据库对象
        try:
            case = Case.objects.get(id=pk, is_delete=False)
        except Case.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 序列化返回
        serializer = CaseSerializer(case)
        return Response(serializer.data)

    def delete(self, request, pk):
        # 根据id, 查询数据库对象
        try:
            case = Case.objects.get(id=pk, is_delete=False)
        except Case.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # 逻辑删除, .save方法适合于单条记录的保存, 而.update方法适用于批量数据的保存
        case.is_delete = True
        case.save()

        return Response(status=status.HTTP_204_NO_CONTENT)