from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("pos/", views.pos, name="pos"),
    path("pos/add/<int:product_id>/", views.pos_add, name="pos_add"),
    path("pos/update/<int:product_id>/", views.pos_update, name="pos_update"),
    path("pos/remove/<int:product_id>/", views.pos_remove, name="pos_remove"),
    path("pos/discount/", views.pos_discount, name="pos_discount"),
    path("pos/checkout/", views.pos_checkout, name="pos_checkout"),
    path("sales/<int:pk>/", views.sale_detail, name="sale_detail"),
]
