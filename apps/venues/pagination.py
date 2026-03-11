from rest_framework.pagination import PageNumberPagination


class VenuePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'   # ?page_size=20 ile override edilebilir
    max_page_size = 100