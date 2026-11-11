from django.urls import path
from . import views

app_name = 'catalogo'

urlpatterns = [
    path('', views.CatalogoView.as_view(), name='catalogo'),
    path('carrito/', views.ver_carrito, name='carrito'),
    path('carrito/agregar/<int:producto_id>/', views.agregar_al_carrito, name='agregar'),
    path('carrito/remover/<int:producto_id>/', views.remover_del_carrito, name='remover'),
    path('carrito/actualizar/<int:producto_id>/', views.actualizar_cantidad, name='actualizar'),
    path('carrito/vaciar/', views.vaciar_carrito, name='vaciar'),
    path('checkout/', views.checkout, name='checkout'),
    path('pago-exitoso/<int:pk>/', views.pago_exitoso, name='pago_exitoso'),
]