# core/views.py
"""Vistas principales del proyecto ERP — W02.

Migración: HttpResponse → render() con templates y contexto.
"""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.crypto import constant_time_compare


def _url(nombre, respaldo='/'):
    """Devuelve la URL de una ruta con nombre; si no existe, usa el respaldo."""
    try:
        return reverse(nombre)
    except NoReverseMatch:
        return respaldo


def bienvenida(request):
    """Página de inicio del ERP con tarjetas de módulos.

    Context:
        modulos (list): Lista de dicts con icono, nombre, url y descripcion.

    Returns:
        HttpResponse con template bienvenida.html.
    """
    modulos = [
        {
            'nombre': 'Productos',
            'icono': '📦',
            'url': _url('productos:inicio', '/productos/'),
            'descripcion': 'Inventario, precios y stock',
        },
        {
            'nombre': 'Clientes',
            'icono': '👥',
            'url': _url('clientes:inicio', '/clientes/'),
            'descripcion': 'Cartera y gestión de clientes',
        },
        {
            'nombre': 'Proveedores',
            'icono': '🏭',
            'url': _url('proveedores:inicio', '/proveedores/'),
            'descripcion': 'Red de proveedores',
        },
        {
            'nombre': 'Ventas',
            'icono': '💰',
            'url': _url('ventas:inicio', '/ventas/'),
            'descripcion': 'Pedidos, facturas y cobros',
        },
        {
            'nombre': 'Reportes',
            'icono': '📊',
            'url': _url('reportes:inicio', '/reportes/'),
            'descripcion': 'Dashboard y analítica',
        },
        {
            'nombre': 'Admin',
            'icono': '⚙️',
            'url': '/admin/',
            'descripcion': 'Panel de administración Django',
        },
    ]
    return render(request, 'bienvenida.html', {'modulos': modulos})


def enviar_reporte_ahora(request):
    """Envía el reporte de ventas al instante.

    - POST: solo usuarios staff con sesión iniciada (botón de la tienda).
    - GET:  ?token=... igual a REPORTE_TOKEN (para cron-job.org),
            o usuario staff con sesión iniciada.
    """
    from core.reportes import construir_contexto_reporte, enviar_reporte_ventas

    if request.method == 'POST':
        autorizado = request.user.is_staff
    else:
        token_esperado = getattr(settings, 'REPORTE_TOKEN', '')
        token = request.GET.get('token', '')
        autorizado = (
            bool(token_esperado) and constant_time_compare(token, token_esperado)
        ) or request.user.is_staff

    if not autorizado:
        return JsonResponse({'estado': 'no autorizado'}, status=403)

    try:
        contexto = construir_contexto_reporte()
        enviar_reporte_ventas(contexto=contexto)
    except Exception as exc:
        return JsonResponse({'estado': 'error', 'detalle': str(exc)}, status=500)

    return JsonResponse({
        'estado': 'enviado',
        'fecha': contexto['fecha'],
        'total_pedidos': contexto['total_pedidos'],
    })