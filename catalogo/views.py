# catalogo/views.py
"""Vistas del módulo de catálogo y carrito — W13.

Módulo público (no requiere autenticación para lectura).
El carrito se almacena en la sesión Django.

Estructura del carrito en sesión:
    request.session['carrito'] = {
        '1': {
            'nombre':   'Laptop HP',
            'precio':   '10000.00',   # str — Decimal no es JSON serializable
            'cantidad': 2,
            'imagen':   'productos/laptop.jpg'  # o None
        },
        ...
    }
"""
import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from productos.models import Producto
from ventas.models import Pedido

from .checkout_utils import (
    armar_items,
    calcular_totales,
    generar_numero_pedido,
    obtener_o_crear_cliente,
)
from .filters import ProductoFilter

logger = logging.getLogger(__name__)


# ── CATÁLOGO ───────────────────────────────────────────────────────────────

class CatalogoView(ListView):
    """Catálogo público de productos con filtros.

    No requiere autenticación — accesible para cualquier visitante.
    """

    model               = Producto
    template_name       = 'catalogo/catalogo.html'
    context_object_name = 'productos'
    paginate_by         = 12    # 3 filas de 4 tarjetas

    def get_queryset(self):
        """Filtra productos activos aplicando los filtros del request."""
        qs = (
            Producto.objects
            .select_related('categoria', 'proveedor')
            .filter(activo=True)
            .order_by('nombre')
        )
        self.filtro = ProductoFilter(self.request.GET, queryset=qs)
        return self.filtro.qs

    def get_context_data(self, **kwargs):
        """Agrega el objeto filtro al contexto para renderizar el formulario."""
        ctx = super().get_context_data(**kwargs)
        ctx['filtro']     = self.filtro
        ctx['categorias'] = self.filtro.form.fields['categoria'].queryset
        return ctx


# ── CARRITO ─────────────────────────────────────────────────────────────────

def _obtener_carrito(request) -> dict:
    """Obtiene el carrito de la sesión o crea uno vacío."""
    return request.session.get('carrito', {})


def _guardar_carrito(request, carrito: dict) -> None:
    """Guarda el carrito en la sesión y marca como modificado."""
    request.session['carrito'] = carrito
    request.session.modified = True


def ver_carrito(request):
    """Muestra el contenido del carrito con el total calculado."""
    carrito = _obtener_carrito(request)

    items = []
    total = Decimal('0.00')

    for prod_id, datos in carrito.items():
        precio   = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        subtotal = precio * cantidad
        total   += subtotal
        items.append({
            'prod_id':  prod_id,
            'nombre':   datos['nombre'],
            'precio':   precio,
            'cantidad': cantidad,
            'subtotal': subtotal,
            'imagen':   datos.get('imagen'),
        })

    return render(request, 'catalogo/carrito.html', {
        'items': items,
        'total': total,
    })


def agregar_al_carrito(request, producto_id: int):
    """Agrega un producto al carrito o incrementa su cantidad. Solo POST."""
    if request.method != 'POST':
        return redirect('catalogo:catalogo')

    producto = get_object_or_404(Producto, pk=producto_id, activo=True)
    carrito  = _obtener_carrito(request)

    clave    = str(producto_id)
    cantidad = int(request.POST.get('cantidad', 1))

    if clave in carrito:
        carrito[clave]['cantidad'] += cantidad
    else:
        carrito[clave] = {
            'nombre':   producto.nombre,
            'precio':   str(producto.precio),
            'cantidad': cantidad,
            'imagen':   producto.imagen.name if producto.imagen else None,
        }

    _guardar_carrito(request, carrito)
    messages.success(request, f'"{producto.nombre}" agregado al carrito.')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    return redirect(next_url or 'catalogo:catalogo')


def remover_del_carrito(request, producto_id: int):
    """Elimina un producto del carrito. Solo POST."""
    if request.method != 'POST':
        return redirect('catalogo:carrito')

    carrito = _obtener_carrito(request)
    clave   = str(producto_id)

    nombre = carrito.get(clave, {}).get('nombre', 'Producto')
    carrito.pop(clave, None)
    _guardar_carrito(request, carrito)

    messages.warning(request, f'"{nombre}" eliminado del carrito.')
    return redirect('catalogo:carrito')


def actualizar_cantidad(request, producto_id: int):
    """Actualiza la cantidad de un producto. Si es 0 o menos, elimina el item. Solo POST."""
    if request.method != 'POST':
        return redirect('catalogo:carrito')

    carrito  = _obtener_carrito(request)
    clave    = str(producto_id)
    cantidad = int(request.POST.get('cantidad', 1))

    if clave in carrito:
        if cantidad > 0:
            carrito[clave]['cantidad'] = cantidad
        else:
            carrito.pop(clave)

    _guardar_carrito(request, carrito)
    return redirect('catalogo:carrito')


def vaciar_carrito(request):
    """Elimina todos los productos del carrito."""
    if request.method == 'POST':
        _guardar_carrito(request, {})
        messages.info(request, 'Carrito vaciado.')
    return redirect('catalogo:carrito')


# ── CHECKOUT Y PAGO ─────────────────────────────────────────────────────────

@login_required
def checkout(request):
    """Resumen del carrito (GET) y creación de Pedido + PaymentIntent (POST).

    En POST, el Pedido guarda un snapshot del carrito en items_snapshot,
    para conservar nombre, cantidad y precio aunque el producto cambie después.
    """
    carrito = _obtener_carrito(request)
    if not carrito:
        messages.warning(request, 'Tu carrito está vacío.')
        return redirect('catalogo:catalogo')

    totales = calcular_totales(carrito)
    items   = armar_items(carrito)

    contexto = {
        'carrito':         carrito,
        'items':           items,
        'totales':         totales,
        'pedido':          None,
        'client_secret':   None,
        'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    }

    if request.method != 'POST':
        return render(request, 'catalogo/checkout.html', contexto)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        cliente = obtener_o_crear_cliente(request.user)

        # Snapshot del carrito: lista de dicts serializables a JSON
        snapshot = [
            {
                'producto_id': int(prod_id),
                'nombre':      datos['nombre'],
                'cantidad':    int(datos['cantidad']),
                'precio':      datos['precio'],   # ya es str
            }
            for prod_id, datos in carrito.items()
        ]

        pedido = Pedido.objects.create(
            numero_pedido  = generar_numero_pedido(),
            cliente        = cliente,
            estado         = 'pendiente',
            total_pagado   = totales['total'],
            items_snapshot = snapshot,
        )

        intent = stripe.PaymentIntent.create(
            amount=int(totales['total'] * 100),  # Stripe usa centavos
            currency='mxn',
            metadata={
                'pedido_id':  pedido.pk,
                'pedido_num': pedido.numero_pedido,
            },
            idempotency_key=f'pedido-{pedido.pk}',
        )

    except stripe.StripeError as exc:
        mensaje = getattr(exc, 'user_message', None) or str(exc)
        messages.error(request, f'Error al conectar con Stripe: {mensaje}')
        return redirect('catalogo:pago_error')

    contexto['pedido']        = pedido
    contexto['client_secret'] = intent.client_secret
    return render(request, 'catalogo/checkout.html', contexto)


@login_required
def pago_exitoso(request, pk):
    """Confirmación post-pago: vacía el carrito y muestra el pedido."""
    pedido = get_object_or_404(Pedido, pk=pk)

    _guardar_carrito(request, {})
    messages.success(
        request,
        f'¡Pago exitoso! Tu pedido {pedido.numero_pedido} '
        f'está confirmado. Total: ${pedido.total_pagado}'
    )
    return render(request, 'catalogo/pago_exitoso.html', {'pedido': pedido})


def pago_error(request):
    """Muestra el error de pago y permite reintentar."""
    return render(request, 'catalogo/pago_error.html')


# ── WEBHOOK DE STRIPE ──────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Recibe eventos de Stripe y marca el Pedido como pagado.

    Stripe no envía token CSRF, por eso la vista es csrf_exempt.
    La firma se verifica con STRIPE_WEBHOOK_SECRET para que nadie
    más pueda marcar pedidos como pagados.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        logger.warning('Webhook: payload inválido recibido.')
        return HttpResponseBadRequest('Payload inválido.')
    except stripe.SignatureVerificationError:
        logger.warning('Webhook: firma inválida — posible ataque.')
        return HttpResponseBadRequest('Firma inválida.')

    if event['type'] == 'payment_intent.succeeded':
        intent = event['data']['object']
        pedido_id = intent.get('metadata', {}).get('pedido_id')
        if pedido_id:
            # filter().update() es idempotente: si Stripe reenvía el evento,
            # el pedido ya no está en 'pendiente' y no cambia nada.
            Pedido.objects.filter(pk=pedido_id, estado='pendiente').update(
                estado='pagado'
            )

    # Otros eventos (por ejemplo payment_failed) no cambian el pedido.
    return HttpResponse(status=200)