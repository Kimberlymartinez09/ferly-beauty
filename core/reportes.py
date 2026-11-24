from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

ESTADO_PAGADO = "pagado"


def construir_contexto_reporte(fecha=None):
    # Import diferido: evita AppRegistryNotReady si este módulo se importa
    # antes de que Django termine de cargar las apps (por ejemplo desde settings)
    from ventas.models import Pedido

    # localdate() respeta TIME_ZONE (America/Mexico_City); date.today() usa la hora del servidor
    fecha = fecha or timezone.localdate()
    fecha_txt = fecha.strftime("%d/%m/%Y")

    pedidos = Pedido.objects.filter(estado=ESTADO_PAGADO, fecha_pedido__date=fecha)

    total = pedidos.aggregate(t=Sum("total_pagado"))["t"] or Decimal("0")

    acumulado = defaultdict(lambda: {"unidades": 0, "ingreso": Decimal("0")})
    for pedido in pedidos:
        for item in pedido.items_snapshot or []:
            nombre = item.get("nombre", "Sin nombre")
            cantidad = int(item.get("cantidad", 0))
            precio = Decimal(str(item.get("precio", "0")))
            acumulado[nombre]["unidades"] += cantidad
            acumulado[nombre]["ingreso"] += precio * cantidad

    top = sorted(acumulado.items(), key=lambda x: x[1]["unidades"], reverse=True)[:5]

    return {
        "fecha": fecha_txt,
        "periodo": fecha_txt,
        "config": {"nombre_empresa": settings.NOMBRE_EMPRESA},
        "nombre_empresa": settings.NOMBRE_EMPRESA,
        "total_pedidos": pedidos.count(),
        "total_facturado": f"{total:,.2f}",
        "top_productos": [
            {
                "nombre": nombre,
                "unidades": datos["unidades"],
                "ingreso": f"{datos['ingreso']:,.2f}",
            }
            for nombre, datos in top
        ],
        "url_admin": f"{settings.SITE_URL}/admin/",
    }


def enviar_reporte_ventas(destinatarios=None, contexto=None):
    # Si no pasas destinatarios, se manda a los ADMINS (tu correo en ADMIN_EMAIL)
    if not destinatarios:
        destinatarios = [correo for _, correo in settings.ADMINS]
    if contexto is None:
        contexto = construir_contexto_reporte()

    nombre = contexto["config"]["nombre_empresa"]
    asunto = f"{nombre} – Reporte de ventas – {contexto['periodo']}"

    html_content = render_to_string("emails/reporte_ventas.html", contexto)
    text_content = render_to_string("emails/reporte_ventas.txt", contexto)

    msg = EmailMultiAlternatives(
        subject=asunto,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatarios,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    return True