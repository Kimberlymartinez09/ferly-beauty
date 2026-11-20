# catalogo/views.py
"""Vistas del módulo de catálogo y carrito — W13/W14.

El catálogo es público. El carrito se guarda en la sesión de Django.
El checkout y la confirmación de pago requieren autenticación.

Estructura del carrito en sesión:
    request.session['carrito'] = {
        '1': {
            'nombre':   'Laptop HP',
            'precio':   '10000.00',   # str: Decimal no es serializable en JSON
            'cantidad': 2,
            'imagen':   'productos/laptop.jpg'  # o None
        },
        ...
    }

Pedido en curso (W14, editado):
    request.session['pedido_pendiente'] = <pk del Pedido en estado 'pendiente'>
    Permite reutilizar el mismo pedido y el mismo PaymentIntent si el
    usuario hace doble clic o recarga la página de pago.
"""
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
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

stripe.api_key = settings.STRIPE_SECRET_KEY

CANTIDAD_MIN = 1
CANTIDAD_MAX = 99


# ── CATÁLOGO ───────────────────────────────────────────────────────────────

class CatalogoView(ListView):
    """Catálogo público de productos con filtros."""

    model               = Producto
    template_name       = 'catalogo/catalogo.html'
    context_object_name = 'productos'
    paginate_by         = 12  # 3 filas de 4 tarjetas

    def get_queryset(self):
        qs = (
            Producto.objects
            .select_related('categoria', 'proveedor')
            .filter(activo=True)
            .order_by('nombre')
        )
        self.filtro = ProductoFilter(self.request.GET, queryset=qs)
        return self.filtro.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtro']     = self.filtro
        ctx['categorias'] = self.filtro.form.fields['categoria'].queryset
        return ctx


# ── HELPERS DEL CARRITO ────────────────────────────────────────────────────

def _obtener_carrito(request) -> dict:
    """Devuelve el carrito de la sesión o un dict vacío."""
    return request.session.get('carrito', {})


def _guardar_carrito(request, carrito: dict) -> None:
    """Guarda el carrito en la sesión y marca la sesión como modificada."""
    request.session['carrito'] = carrito
    request.session.modified = True


def _leer_cantidad(request, default: int = 1) -> int:
    """Lee la cantidad del POST y la acota entre CANTIDAD_MIN y CANTIDAD_MAX.

    Valores no numéricos devuelven el default. No permite 0 ni negativos;
    actualizar_cantidad maneja el caso 0 por separado.
    """
    try:
        valor = int(request.POST.get('cantidad', default))
    except (TypeError, ValueError):
        return default
    return max(CANTIDAD_MIN, min(valor, CANTIDAD_MAX))


def _sincronizar_precios(request, carrito: dict) -> dict:
    """Actualiza nombre, precio e imagen del carrito con los datos de la BD.

    Quita del carrito los productos que ya no existen o están inactivos.
    Así el monto que se cobra en Stripe siempre sale de la base de datos,
    no de lo que se guardó en la sesión.
    """
    if not carrito:
        return carrito

    ids = [int(pid) for pid in carrito.keys()]
    productos = Producto.objects.filter(pk__in=ids, activo=True)
    por_id = {str(p.pk): p for p in productos}

    actualizado = {}
    for clave, datos in carrito.items():
        producto = por_id.get(clave)
        if producto is None:
            continue  # producto eliminado o desactivado
        actualizado[clave] = {
            'nombre':   producto.nombre,
            'precio':   str(producto.precio),
            'cantidad': int(datos['cantidad']),
            'imagen':   producto.imagen.name if producto.imagen else None,
        }

    if actualizado != carrito:
        _guardar_carrito(request, actualizado)

    return actualizado


def _obtener_pedido_pendiente(request, cliente, snapshot: list, total: Decimal) -> Pedido:
    """Devuelve el pedido pendiente de la sesión o crea uno nuevo.

    Si el usuario hace doble clic o recarga la página de pago, se reutiliza
    el mismo Pedido (y, con él, el mismo PaymentIntent en Stripe). Si el
    carrito cambió, se actualizan total y snapshot del pedido existente.
    """
    pedido = None
    pedido_id = request.session.get('pedido_pendiente')
    if pedido_id:
        pedido = (
            Pedido.objects
            .filter(pk=pedido_id, cliente=cliente, estado='pendiente')
            .first()
        )

    if pedido is None:
        pedido = Pedido.objects.create(
            numero_pedido  = generar_numero_pedido(),
            cliente        = cliente,
            estado         = 'pendiente',
            total_pagado   = total,
            items_snapshot = snapshot,
        )
    else:
        pedido.total_pagado   = total
        pedido.items_snapshot = snapshot
        pedido.save(update_fields=['total_pagado', 'items_snapshot'])

    request.session['pedido_pendiente'] = pedido.pk
    request.session.modified = True
    return pedido


# ── CARRITO ────────────────────────────────────────────────────────────────

def ver_carrito(request):
    """Muestra el contenido del carrito con el total calculado."""
    carrito = _sincronizar_precios(request, _obtener_carrito(request))

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
    """Agrega un producto o incrementa su cantidad. Solo POST."""
    if request.method != 'POST':
        return redirect('catalogo:catalogo')

    producto = get_object_or_404(Producto, pk=producto_id, activo=True)
    carrito  = _obtener_carrito(request)
    clave    = str(producto_id)
    cantidad = _leer_cantidad(request)

    if clave in carrito:
        nueva = int(carrito[clave]['cantidad']) + cantidad
        carrito[clave]['cantidad'] = min(nueva, CANTIDAD_MAX)
        # Actualiza nombre, precio e imagen por si cambiaron
        carrito[clave]['nombre'] = producto.nombre
        carrito[clave]['precio'] = str(producto.precio)
        carrito[clave]['imagen'] = producto.imagen.name if producto.imagen else None
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
    """Cambia la cantidad de un producto. Si es 0 o menos, lo elimina. Solo POST."""
    if request.method != 'POST':
        return redirect('catalogo:carrito')

    carrito = _obtener_carrito(request)
    clave   = str(producto_id)

    try:
        valor = int(request.POST.get('cantidad', 1))
    except (TypeError, ValueError):
        valor = 1

    if clave in carrito:
        if valor <= 0:
            carrito.pop(clave)
        else:
            carrito[clave]['cantidad'] = min(valor, CANTIDAD_MAX)

    _guardar_carrito(request, carrito)
    return redirect('catalogo:carrito')


def vaciar_carrito(request):
    """Elimina todos los productos del carrito. Solo POST."""
    if request.method == 'POST':
        _guardar_carrito(request, {})
        messages.info(request, 'Carrito vaciado.')
    return redirect('catalogo:carrito')


# ── CHECKOUT Y PAGO ────────────────────────────────────────────────────────

@login_required
def checkout(request):
    """Resumen del carrito (GET) y creación del pedido + PaymentIntent (POST).

    Los precios se vuelven a leer de la base de datos antes de calcular
    el monto, así que el cobro nunca usa precios viejos de la sesión.
    """
    carrito = _sincronizar_precios(request, _obtener_carrito(request))
    if not carrito:
        messages.warning(request, 'Tu carrito está vacío.')
        return redirect('catalogo:catalogo')

    totales         = calcular_totales(carrito)
    items           = armar_items(carrito)
    publishable_key = settings.STRIPE_PUBLISHABLE_KEY

    if request.method == 'POST':
        try:
            # 1. Vincular el usuario con el Cliente del ERP
            cliente = obtener_o_crear_cliente(request.user)

            # 2. Snapshot del carrito y pedido pendiente (reutilizado si existe)
            snapshot = [
                {
                    'producto_id': int(prod_id),
                    'nombre':      datos['nombre'],
                    'cantidad':    int(datos['cantidad']),
                    'precio':      datos['precio'],  # str
                }
                for prod_id, datos in carrito.items()
            ]
            pedido = _obtener_pedido_pendiente(
                request, cliente, snapshot, totales['total']
            )

            # 3. PaymentIntent en Stripe (monto en centavos).
            #    La clave incluye el monto: si el carrito cambia, Stripe no
            #    confunde el intento nuevo con el anterior.
            monto_centavos = int(totales['total'] * 100)

            intent = stripe.PaymentIntent.create(
                amount          = monto_centavos,
                currency        = 'mxn',
                metadata        = {
                    'pedido_id':  pedido.pk,
                    'pedido_num': pedido.numero_pedido,
                    'cliente':    cliente.nombre,
                },
                idempotency_key = f'pedido-{pedido.pk}-{monto_centavos}',
            )

            # 4. Devolver client_secret al template
            return render(request, 'catalogo/checkout.html', {
                'carrito':         carrito,
                'items':           items,
                'totales':         totales,
                'pedido':          pedido,
                'client_secret':   intent.client_secret,
                'publishable_key': publishable_key,
            })

        except stripe.StripeError as exc:
            messages.error(
                request,
                f'Error al conectar con Stripe: {exc.user_message}'
            )
            return redirect('catalogo:pago_error')

        except Exception as exc:
            messages.error(
                request,
                f'Error inesperado en el proceso de pago: {exc}'
            )
            return redirect('catalogo:pago_error')

    # GET: solo resumen, sin PaymentIntent
    return render(request, 'catalogo/checkout.html', {
        'carrito':         carrito,
        'items':           items,
        'totales':         totales,
        'client_secret':   None,
        'publishable_key': publishable_key,
    })


@login_required
def pago_exitoso(request, pedido_id: int):
    """Confirmación post-pago. Solo muestra pedidos del cliente actual.

    No marca el pedido como pagado: eso lo hace el webhook
    de Stripe (payment_intent.succeeded). W16: esta vista NO encola
    la tarea de correo; la encola el webhook.
    """
    cliente = obtener_o_crear_cliente(request.user)
    pedido  = get_object_or_404(Pedido, pk=pedido_id, cliente=cliente)

    _guardar_carrito(request, {})
    request.session.pop('pedido_pendiente', None)  # el intento ya terminó

    messages.success(
        request,
        f'Pago recibido. Tu pedido {pedido.numero_pedido} está en proceso. '
        f'Total: ${pedido.total_pagado}'
    )
    return render(request, 'catalogo/pago_exitoso.html', {'pedido': pedido})


def pago_error(request):
    """Muestra el error de pago y permite reintentar."""
    return render(request, 'catalogo/pago_error.html')